"""Shared implementation of SMART's ``get`` / ``set`` RS-232 console protocol.

Most commands in the SMART command reference follow one convention:

* ``get <key>``                      -> ``<key>=<value>``
* ``set <key>=<value>``              -> ``<key>=<confirmed value>``
* ``set <key>+<n>`` / ``set <key>-<n>``   (relative adjustment)
* ``set <key> <source>=<value>``     (target a currently inactive video source)
* bare verbs such as ``on`` / ``off`` for power

:class:`SmartDevice` implements that convention once, on top of any
:class:`~smart_serial.transport.Transport`, so a new SMART model only has to
declare its settings.

Retry policy
~~~~~~~~~~~~
A *timeout* is ambiguous: the device may have executed the command and the reply
was merely lost or late. Re-sending is therefore only done for idempotent
commands (``get``, absolute ``set``, ``on``). Re-sending ``off`` would confirm a
shutdown the caller never asked for, and re-sending ``set volume+5`` would apply
it twice. A *garbled* command (the device answers ``invalid cmd=`` with text other
than what we sent) was rejected, i.e. **not** executed, so it is always safe to
send again.
"""

from __future__ import annotations

import logging
import re
from enum import StrEnum
from typing import Any, Self

from ..device import Device
from ..exceptions import (
    CommandRejectedError,
    DeviceIdleError,
    SerialTimeoutError,
    SmartSerialError,
)
from ..source import Source
from .settings import ReadOnlySetting

_LOGGER = logging.getLogger(__name__)

_LINE_SPLIT_RE = re.compile(r"[\r\n]+")
_MAX_ATTEMPTS = 3
_INVALID_PREFIX = "invalid cmd="
_POWER_STATE_QUERY = "get powerstate"


class CaseInsensitiveStrEnum(StrEnum):
    """A :class:`~enum.StrEnum` whose lookup by value ignores case and outer whitespace.

    The vendor manual isn't consistent about casing (``SMARTpresentation``,
    ``brightroom``, ``sRGB``), so replies are matched leniently.
    """

    @classmethod
    def _missing_(cls, value: object) -> Self | None:
        if isinstance(value, str):
            folded = value.strip().casefold()
            for member in cls:
                if member.value.casefold() == folded:
                    return member
        return None


def select_reply(text: str) -> str:
    """Pick the meaningful line out of the raw text that preceded the prompt.

    The reply is the last line containing ``=``; failing that, the last non-empty
    line. Returns ``""`` if there is nothing.
    """
    lines = [line.strip() for line in _LINE_SPLIT_RE.split(text) if line.strip()]
    for line in reversed(lines):
        if "=" in line:
            return line
    return lines[-1] if lines else ""


def _rejected_command(reply: str) -> str | None:
    """If ``reply`` is ``invalid cmd=<x>``, return ``<x>`` normalized; else ``None``."""
    if reply.lower().startswith(_INVALID_PREFIX):
        return reply.split("=", 1)[1].strip().lower()
    return None


class SmartDevice(Device):
    """Base class for SMART devices that speak the ``get`` / ``set`` console protocol."""

    # ------------------------------------------------------------ generic access

    async def get_value(self, key: str) -> str:
        """Send ``get <key>`` and return the raw value from the reply."""
        reply = await self._send(f"get {key}", retry_on_timeout=True)
        return self._extract_value(reply)

    async def set_value(self, key: str, value: str, *, source: Source | str | None = None) -> str:
        """Send ``set <key>[ <source>]=<value>`` and return the confirmed raw value.

        ``source`` targets a currently-inactive video source (e.g. ``"vga1"``)
        rather than the active one. Only some ``set`` commands support this; check
        the command's table in the vendor reference.
        """
        reply = await self._send(f"set {self._target(key, source)}={value}", retry_on_timeout=True)
        return self._extract_value(reply)

    async def adjust_value(
        self, key: str, delta: int, *, source: Source | str | None = None
    ) -> str:
        """Send a relative adjustment, e.g. ``set brightness+5`` / ``set brightness-15``.

        Never re-sent after a timeout, because the adjustment might already have applied.
        """
        sign = "+" if delta >= 0 else "-"
        reply = await self._send(
            f"set {self._target(key, source)}{sign}{abs(delta)}", retry_on_timeout=False
        )
        return self._extract_value(reply)

    async def send_verb(self, verb: str, *, retry_on_timeout: bool = False) -> str:
        """Send a bare verb (``on``, ``off``, ...) and return the raw value from the reply."""
        return self._extract_value(await self._send(verb, retry_on_timeout=retry_on_timeout))

    # ------------------------------------------------------------- introspection

    @classmethod
    def settings(cls) -> dict[str, ReadOnlySetting[Any]]:
        """Every declared setting of this class (including inherited ones), by attribute name."""
        found: dict[str, ReadOnlySetting[Any]] = {}
        for klass in reversed(cls.__mro__):
            for name, attr in vars(klass).items():
                if isinstance(attr, ReadOnlySetting):
                    found[name] = attr
        return found

    # ----------------------------------------------------------------- internals

    @staticmethod
    def _target(key: str, source: Source | str | None) -> str:
        return key if source is None else f"{key} {Source.coerce(source)}"

    @staticmethod
    def _extract_value(reply: str) -> str:
        _, separator, value = reply.partition("=")
        return value if separator else reply

    async def _send(self, command: str, *, retry_on_timeout: bool) -> str:
        """Exchange one command and return the selected reply line.

        Raises:
            ValueError: ``command`` contains a line break (it would smuggle in a second command).
            SerialTimeoutError, ConnectionLostError, ...: from the transport.
            CommandRejectedError / DeviceIdleError: the device rejected the command.
        """
        if "\r" in command or "\n" in command:
            raise ValueError(f"Command must not contain line breaks: {command!r}")

        for attempt in range(1, _MAX_ATTEMPTS + 1):
            is_last = attempt == _MAX_ATTEMPTS
            try:
                text = await self.transport.exchange(command)
            except SerialTimeoutError:
                if retry_on_timeout and not is_last:
                    _LOGGER.debug("Timeout on %r (attempt %d), retrying", command, attempt)
                    continue
                raise

            reply = select_reply(text)
            rejected = _rejected_command(reply)
            if rejected is None:
                return reply
            if rejected == command.strip().lower():
                raise await self._rejection_error(command, reply)
            if is_last:
                raise CommandRejectedError(command, reply)
            _LOGGER.debug("Garbled command %r (got %r), resending", command, reply)

        raise AssertionError("unreachable")  # pragma: no cover

    async def _rejection_error(self, command: str, reply: str) -> CommandRejectedError:
        """Build the exception for a rejected command.

        A rejection can mean "unsupported right now" (e.g. a VGA-only setting while
        on HDMI) or "the device is idle". Ask for the power state to tell them apart.
        """
        if command.strip().lower() != _POWER_STATE_QUERY and await self._is_idle():
            return DeviceIdleError(command, reply)
        return CommandRejectedError(command, reply)

    async def _is_idle(self) -> bool:
        try:
            reply = await self._send(_POWER_STATE_QUERY, retry_on_timeout=True)
        except SmartSerialError:
            return False
        return self._extract_value(reply).strip().lower() == "idle"
