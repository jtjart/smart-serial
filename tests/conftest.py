"""Shared fixtures.

Tests are plain synchronous functions that call ``asyncio.run(...)``, so they run
unchanged whether or not the repo uses pytest-asyncio / anyio.
"""

from __future__ import annotations

from collections import deque

import pytest

from smart_serial import SmartUX60


class FakeTransport:
    """In-memory :class:`~smart_serial.Transport`: replays scripted replies, records commands.

    Queue raw reply text (what the real transport returns: everything before the
    prompt) or an exception to raise. Running out of replies fails the test.
    """

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.connect_calls = 0
        self.disconnect_calls = 0
        self._connected = False
        self._replies: deque[str | BaseException] = deque()

    def queue(self, *replies: str | BaseException) -> None:
        self._replies.extend(replies)

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self.connect_calls += 1
        self._connected = True

    async def disconnect(self) -> None:
        self.disconnect_calls += 1
        self._connected = False

    async def exchange(self, command: str) -> str:
        self.sent.append(command)
        if not self._replies:
            raise AssertionError(f"Unexpected command with no scripted reply: {command!r}")
        reply = self._replies.popleft()
        if isinstance(reply, BaseException):
            raise reply
        return reply


@pytest.fixture
def fake() -> FakeTransport:
    return FakeTransport()


@pytest.fixture
def projector(fake: FakeTransport) -> SmartUX60:
    return SmartUX60(fake)
