"""Asynchronous, prompt-delimited transport over a serial (RS-232) connection.

This implements the command-line-style RS-232 protocol used by SMART
Technologies AV hardware (confirmed against the SMART UX60 projector's
"RS-232 Programming Commands" reference): commands are ASCII, terminated
by a carriage return, and every response -- successful or not -- is
followed by a ``>`` command prompt that signals the device is ready for
the next command. A command must not be sent while that prompt is still
pending; before each write, we consume any stale prompt already waiting in
buffer so the next command is sent only after the device has signalled it
is ready. The hardware guide also requires roughly 10 ms between
characters for reliable operation, so writes are paced accordingly.
"""

from __future__ import annotations

import asyncio
import logging
import re

import serial_asyncio_fast as serial_asyncio

from .exceptions import (
    CommandError,
    ConnectionNotEstablishedError,
    DeviceIdleError,
    SerialTimeoutError,
)

_LOGGER = logging.getLogger(__name__)

_LINE_SPLIT_RE = re.compile(rb"[\r\n]+")


class SerialTransport:
    """Thin async wrapper around a serial port speaking a prompt-based ASCII protocol.

    Each call to :meth:`send_command` writes one command (a line ending is
    appended) and reads everything up to the device's next command prompt,
    returning the last non-empty line before that prompt -- which is where
    this protocol places the actual ``key=value`` reply. Access is
    serialized with an internal lock, so it's safe to call
    :meth:`send_command` concurrently from multiple coroutines: calls
    queue up rather than interleaving on the wire.
    """

    def __init__(
        self,
        port: str,
        *,
        baudrate: int = 19200,
        bytesize: int = 8,
        parity: str = "N",
        stopbits: float = 1,
        line_ending: bytes = b"\r",
        prompt: bytes = b">",
        encoding: str = "ascii",
        inter_character_delay: float = 0.01,
        response_timeout: float = 2.0,
        connect_timeout: float = 5.0,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.line_ending = line_ending
        self.prompt = prompt
        self.encoding = encoding
        self.inter_character_delay = inter_character_delay
        self.response_timeout = response_timeout
        self.connect_timeout = connect_timeout

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        """Open the serial port. Safe to call again if already connected."""
        if self.is_connected:
            return
        _LOGGER.debug("Opening serial connection to %s @ %d baud", self.port, self.baudrate)
        reader, writer = await asyncio.wait_for(
            serial_asyncio.open_serial_connection(
                url=self.port,
                baudrate=self.baudrate,
                bytesize=self.bytesize,
                parity=self.parity,
                stopbits=self.stopbits,
            ),
            timeout=self.connect_timeout,
        )
        self._reader, self._writer = reader, writer
        # Discard whatever's sitting in the OS receive buffer -- e.g. a
        # leftover ">" prompt from before we connected -- so the first
        # real command's response isn't confused with stale bytes.
        try:
            writer.transport.serial.reset_input_buffer()  # type: ignore[attr-defined]
        except Exception:
            _LOGGER.debug("Could not reset input buffer on %s", self.port, exc_info=True)

    async def disconnect(self) -> None:
        """Close the serial port. Safe to call even if never connected."""
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                _LOGGER.debug("Error while closing %s", self.port, exc_info=True)
        self._reader = None
        self._writer = None

    async def __aenter__(self) -> SerialTransport:
        await self.connect()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.disconnect()

    async def _drain_ready_prompt(self) -> None:
        """Consume a pending prompt before sending a new command.

        Some serial adapters leave a stale ``>`` prompt in the receive buffer
        after connect or after a previous failed call. This makes sure we
        never send a command while the projector still thinks the previous
        one is complete and waiting for the next command.
        """
        if self._reader is None:
            return

        try:
            raw = await asyncio.wait_for(self._reader.readuntil(self.prompt), timeout=0.05)
        except (asyncio.TimeoutError, asyncio.IncompleteReadError):
            return

        _LOGGER.debug("Discarded pending prompt before write: %r", raw)

    async def send_command(self, command: str) -> str:
        """Send ``command`` and return the device's reply line.

        Retry a few times on garbled wake-up responses. If the projector
        reports the same invalid command back, it is treated as an idle-state
        error; otherwise the command is retried until it succeeds or fails.
        """
        if not self.is_connected or self._reader is None or self._writer is None:
            raise ConnectionNotEstablishedError(self.port)

        max_retries = 3
        for attempt in range(max_retries):
            async with self._lock:
                await self._drain_ready_prompt()

                payload = command.encode(self.encoding) + self.line_ending
                _LOGGER.debug("-> %r", payload)
                for i, byte in enumerate(payload):
                    self._writer.write(bytes((byte,)))
                    if i < len(payload) - 1:
                        await asyncio.sleep(self.inter_character_delay)
                await self._writer.drain()

                try:
                    raw = await asyncio.wait_for(
                        self._reader.readuntil(self.prompt), timeout=self.response_timeout
                    )
                except (asyncio.TimeoutError, asyncio.IncompleteReadError) as exc:
                    if attempt < max_retries - 1:
                        continue
                    raise SerialTimeoutError(self.port, command) from exc

                body = raw[: -len(self.prompt)]
                lines = [line for line in _LINE_SPLIT_RE.split(body) if line.strip()]
                decoded = [line.decode(self.encoding, errors="replace").strip() for line in lines]

                response = decoded[-1] if decoded else ""
                if any("=" in line for line in decoded):
                    response = next(
                        (line for line in reversed(decoded) if "=" in line),
                        response,
                    )

                _LOGGER.debug("<- %r", response)

                normalized = response.lower()
                if normalized.startswith("invalid cmd="):
                    invalid_value = response.split("=", 1)[1].strip() if "=" in response else ""
                    invalid_cmd = invalid_value.lower().strip()
                    sent_cmd = command.lower().strip()
                    if invalid_cmd == sent_cmd:
                        raise DeviceIdleError(command, response)
                    if attempt < max_retries - 1:
                        continue
                    raise CommandError(command, response)
                return response

        raise CommandError(command, "retry limit exhausted")
