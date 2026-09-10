from __future__ import annotations

import asyncio

import pytest

from smart_serial.exceptions import DeviceIdleError
from smart_serial.transport import SerialTransport


class _DummyReader:
    async def readuntil(self, _marker: bytes) -> bytes:
        return b"get volume\r\nvolume=12\r>"


class _DummyWriter:
    def __init__(self) -> None:
        self.written: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.written.append(data)

    async def drain(self) -> None:
        return None

    def is_closing(self) -> bool:
        return False


async def test_connect_and_disconnect_lifecycle() -> None:
    """Exercises the real serial_asyncio_fast connection path end to end.

    Uses pySerial's built-in ``loop://`` virtual port so no real hardware
    is needed. Note: this doesn't do an actual write/read round-trip --
    combined with the non-blocking write timeout that serial_asyncio_fast
    configures, pyserial's loop:// handler treats *any* non-empty write as
    exceeding it (it estimates transmission time from the baud rate and
    compares it against a write_timeout of 0), which is a quirk of that
    test-only virtual port rather than of real hardware. Command
    formatting/response handling in :meth:`SerialTransport.send_command` is
    covered instead via the ``fake_transport`` fixture in the device tests.
    """
    transport = SerialTransport("loop://")
    assert not transport.is_connected

    await transport.connect()
    assert transport.is_connected

    await transport.connect()  # calling connect() again should be a no-op
    assert transport.is_connected

    await transport.disconnect()
    assert not transport.is_connected

    await transport.disconnect()  # calling disconnect() again should be a no-op


async def test_send_command_raises_device_idle_error_for_matching_invalid_cmd() -> None:
    class _Reader:
        async def readuntil(self, _prompt: bytes) -> bytes:
            return b"invalid cmd=get modelnum\r>"

    transport = SerialTransport("loop://")
    transport._reader = _Reader()
    transport._writer = _DummyWriter()

    try:
        await transport.send_command("get modelnum")
    except DeviceIdleError as exc:
        assert exc.response == "invalid cmd=get modelnum"
        return

    raise AssertionError("DeviceIdleError was not raised")


async def test_send_command_consumes_pending_prompt_before_writing() -> None:
    class _Reader:
        def __init__(self) -> None:
            self.calls = 0

        async def readuntil(self, _prompt: bytes) -> bytes:
            self.calls += 1
            if self.calls == 1:
                return b">"
            return b"powerstate=On\r>"

    transport = SerialTransport("loop://")
    transport._reader = _Reader()
    transport._writer = _DummyWriter()
    transport._lock = asyncio.Lock()

    assert await transport.send_command("get powerstate") == "powerstate=On"


async def test_send_command_paces_writes_at_10ms_intervals(monkeypatch: pytest.MonkeyPatch) -> None:
    sleep_calls: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    transport = SerialTransport("loop://", inter_character_delay=0.01)
    transport._reader = _DummyReader()
    transport._writer = _DummyWriter()
    transport._lock = asyncio.Lock()

    assert await transport.send_command("get volume") == "volume=12"
    assert len(sleep_calls) == 10
    assert sleep_calls == [0.01] * 10


async def test_send_command_retries_after_timeout() -> None:
    class _Reader:
        def __init__(self) -> None:
            self.calls = 0

        async def readuntil(self, _prompt: bytes) -> bytes:
            self.calls += 1
            if self.calls == 1:
                raise asyncio.TimeoutError
            return b"powerstate=On\r>"

    transport = SerialTransport("loop://")
    transport._reader = _Reader()
    transport._writer = _DummyWriter()

    assert await transport.send_command("get powerstate") == "powerstate=On"


async def test_send_command_retries_for_mismatched_invalid_command() -> None:
    class _Reader:
        def __init__(self) -> None:
            self.calls = 0

        async def readuntil(self, _prompt: bytes) -> bytes:
            self.calls += 1
            if self.calls == 1:
                return b"invalid cmd=get gientp puotw\r>"
            return b"input=HDMI\r>"

    transport = SerialTransport("loop://")
    transport._reader = _Reader()
    transport._writer = _DummyWriter()

    assert await transport.send_command("get input") == "input=HDMI"


async def test_send_command_prefers_key_value_reply_over_echoed_command() -> None:
    """Some devices echo the command before returning the actual value."""
    transport = SerialTransport("loop://")
    transport._reader = _DummyReader()
    transport._writer = _DummyWriter()
    transport._lock = asyncio.Lock()

    assert await transport.send_command("get volume") == "volume=12"
