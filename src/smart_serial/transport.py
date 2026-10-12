"""Asynchronous, prompt-delimited transport over a serial (RS-232) connection.

This layer knows about *framing* only, not about what the bytes mean. It
implements the command-line-style RS-232 protocol used by SMART Technologies
AV hardware (confirmed against the SMART UX60 projector's "RS-232 Programming
Commands" reference): commands are ASCII, terminated by a carriage return, and
every response -- successful or not -- is followed by a ``>`` command prompt
that signals the device is ready for the next command.

Two rules from the hardware guide are enforced here:

* A command must not be sent while a prompt is still pending, so any stale
  bytes are discarded before a write -- but only when the previous exchange did
  not complete cleanly (after connect, or after an error). In the steady state
  every exchange consumes its own prompt, so nothing needs draining and
  commands are not delayed.
* Roughly 10 ms is needed between characters, so writes are paced.

Interpreting replies (``key=value``, ``invalid cmd=``), retries and idempotency
live one layer up, in :class:`smart_serial.devices.base.SmartDevice`.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol

import serial_asyncio_fast as serial_asyncio

from .exceptions import (
    ConnectionFailedError,
    ConnectionLostError,
    ConnectionNotEstablishedError,
    SerialTimeoutError,
)

_LOGGER = logging.getLogger(__name__)

# Upper bound on read() calls while discarding stale bytes, so a device that
# streams continuously can't keep us in the drain loop forever.
_MAX_DRAIN_READS = 32


@dataclass(frozen=True, slots=True)
class SerialSettings:
    """Line settings and protocol framing for a serial device.

    The defaults match the SMART UX60 (19200 8N1, ``\\r``-terminated commands,
    ``>`` prompt). Each device class declares its own via
    :attr:`Device.serial_settings`; use :func:`dataclasses.replace` to tweak one.
    """

    baudrate: int = 19200
    bytesize: int = 8
    parity: str = "N"
    stopbits: float = 1
    line_ending: bytes = b"\r"
    prompt: bytes = b">"
    encoding: str = "ascii"
    inter_character_delay: float = 0.01
    response_timeout: float = 2.0
    connect_timeout: float = 5.0
    drain_timeout: float = 0.05


class Transport(Protocol):
    """What a :class:`~smart_serial.Device` needs from its transport.

    :class:`SerialTransport` is the real implementation; tests can pass any
    object with these members.
    """

    @property
    def is_connected(self) -> bool: ...

    async def connect(self) -> None: ...

    async def disconnect(self) -> None: ...

    async def exchange(self, command: str) -> str:
        """Send ``command`` and return everything the device sent before its next prompt."""
        ...


class SerialTransport:
    """Thin async wrapper around a serial port speaking a prompt-based ASCII protocol.

    Each call to :meth:`exchange` writes one command (a line ending is appended)
    and reads up to the device's next command prompt. Access is serialized with an
    internal lock, so it is safe to call :meth:`exchange` concurrently from
    multiple coroutines: calls queue up rather than interleaving on the wire.
    """

    def __init__(self, port: str, settings: SerialSettings | None = None) -> None:
        self.port: str = port
        self.settings: SerialSettings = settings if settings is not None else SerialSettings()

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()
        self._connect_lock = asyncio.Lock()
        self._needs_drain = False

    @property
    def is_connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        """Open the serial port. Safe to call again, or concurrently, if already connected."""
        async with self._connect_lock:
            if self.is_connected:
                return
            await self._open()

    async def _open(self) -> None:
        s = self.settings
        _LOGGER.debug("Opening serial connection to %s @ %d baud", self.port, s.baudrate)
        try:
            reader, writer = await asyncio.wait_for(
                serial_asyncio.open_serial_connection(
                    url=self.port,
                    baudrate=s.baudrate,
                    bytesize=s.bytesize,
                    parity=s.parity,
                    stopbits=s.stopbits,
                ),
                timeout=s.connect_timeout,
            )
        except (OSError, TimeoutError) as exc:  # SerialException is an OSError
            raise ConnectionFailedError(self.port, str(exc) or type(exc).__name__) from exc
        self._reader, self._writer = reader, writer
        # Discard whatever is sitting in the OS receive buffer -- e.g. a leftover
        # ">" prompt from before we connected -- and drain anything that still
        # trickles in before the first real command.
        try:
            writer.transport.serial.reset_input_buffer()  # type: ignore[attr-defined]
        except Exception:
            _LOGGER.debug("Could not reset input buffer on %s", self.port, exc_info=True)
        self._needs_drain = True

    async def disconnect(self) -> None:
        """Close the serial port. Safe to call even if never connected."""
        await self._close()

    async def __aenter__(self) -> SerialTransport:
        await self.connect()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.disconnect()

    async def exchange(self, command: str) -> str:
        """Send ``command`` and return the reply text that preceded the next prompt.

        The text may span several lines (CR/LF included); picking the meaningful
        one is the caller's job.

        Raises:
            ConnectionNotEstablishedError: not connected.
            SerialTimeoutError: no prompt arrived within ``response_timeout``.
            ConnectionLostError: the port was closed or failed at any point of the
                exchange, including while discarding stale bytes before the write.
        """
        async with self._lock:
            reader, writer = self._require_connection()
            s = self.settings
            try:
                if self._needs_drain:
                    await self._drain_stale(reader)
                # Assume the worst until a complete reply has been read.
                self._needs_drain = True
                await self._write_paced(writer, command)
                raw = await asyncio.wait_for(reader.readuntil(s.prompt), timeout=s.response_timeout)
            except TimeoutError as exc:
                raise SerialTimeoutError(self.port, command) from exc
            except (asyncio.IncompleteReadError, OSError) as exc:
                await self._close()
                raise ConnectionLostError(self.port, str(exc) or type(exc).__name__) from exc
            self._needs_drain = False
            reply = raw[: -len(s.prompt)].decode(s.encoding, errors="replace")
            _LOGGER.debug("<- %r", reply)
            return reply

    def _require_connection(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        if not self.is_connected or self._reader is None or self._writer is None:
            raise ConnectionNotEstablishedError(self.port)
        return self._reader, self._writer

    async def _write_paced(self, writer: asyncio.StreamWriter, command: str) -> None:
        s = self.settings
        payload = command.encode(s.encoding) + s.line_ending
        _LOGGER.debug("-> %r", payload)
        for i, byte in enumerate(payload):
            if writer.is_closing():
                raise ConnectionResetError("connection closed while writing")
            writer.write(bytes((byte,)))
            if i < len(payload) - 1 and s.inter_character_delay > 0:
                await asyncio.sleep(s.inter_character_delay)
        await writer.drain()

    async def _drain_stale(self, reader: asyncio.StreamReader) -> None:
        """Discard bytes already waiting (a stale prompt, wake-up noise) before writing."""
        for _ in range(_MAX_DRAIN_READS):
            try:
                chunk = await asyncio.wait_for(
                    reader.read(1024), timeout=self.settings.drain_timeout
                )
            except TimeoutError:
                return
            if not chunk:  # EOF; the next read will report the lost connection
                return
            _LOGGER.debug("Discarded stale bytes before write: %r", chunk)

    async def _close(self) -> None:
        writer, self._reader, self._writer = self._writer, None, None
        self._needs_drain = False
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                _LOGGER.debug("Error while closing %s", self.port, exc_info=True)
