"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from smart_serial.transport import SerialTransport


class FakeTransport(SerialTransport):
    """A transport double that returns canned responses instead of touching hardware.

    Subclassing the real :class:`SerialTransport` (rather than duck-typing
    an unrelated class) keeps this usable anywhere a real transport is
    expected, while letting device-driver tests run with no serial
    hardware, and no event loop I/O, at all.
    """

    def __init__(self) -> None:
        super().__init__(port="loop://test")
        self.sent: list[str] = []
        self.responses: dict[str, str] = {}
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def send_command(self, command: str) -> str:
        self.sent.append(command)
        return self.responses.get(command, "")


@pytest.fixture
def fake_transport() -> FakeTransport:
    return FakeTransport()
