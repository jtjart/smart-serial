"""SerialTransport framing, tested against an in-memory fake port (no hardware)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest

from smart_serial import (
    ConnectionFailedError,
    ConnectionLostError,
    ConnectionNotEstablishedError,
    SerialSettings,
    SerialTimeoutError,
    SerialTransport,
)

FAST = SerialSettings(
    inter_character_delay=0, response_timeout=0.2, connect_timeout=0.5, drain_timeout=0.01
)


class _FakeSerial:
    def __init__(self) -> None:
        self.input_resets = 0

    def reset_input_buffer(self) -> None:
        self.input_resets += 1


class _FakeAsyncTransport:
    def __init__(self) -> None:
        self.serial = _FakeSerial()


class FakeWriter:
    """Stands in for asyncio.StreamWriter; calls ``on_line`` per complete command."""

    def __init__(self, on_line: Callable[[str], None] | None = None) -> None:
        self.writes: list[bytes] = []
        self.closed = False
        self.transport = _FakeAsyncTransport()
        self._buffer = b""
        self._on_line = on_line

    def write(self, data: bytes) -> None:
        self.writes.append(data)
        self._buffer += data
        while b"\r" in self._buffer:
            line, self._buffer = self._buffer.split(b"\r", 1)
            if self._on_line is not None:
                self._on_line(line.decode())

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    def is_closing(self) -> bool:
        return self.closed

    async def wait_closed(self) -> None:
        return None


class FakePort:
    """A fake serial port whose 'device' answers commands.

    The StreamReader must be created inside the running loop, so it is built lazily
    when the transport opens the port; ``reader`` / ``writer`` are available afterwards.
    """

    def __init__(self, reply_for: Callable[[str], bytes | None], preload: bytes = b"") -> None:
        self._reply_for = reply_for
        self._preload = preload
        self.reader: asyncio.StreamReader | None = None
        self.writer = FakeWriter(self._on_line)

    def _on_line(self, command: str) -> None:
        reply = self._reply_for(command)
        if reply is not None:
            assert self.reader is not None
            self.reader.feed_data(reply)

    async def open(self, **_: object) -> tuple[asyncio.StreamReader, FakeWriter]:
        self.reader = asyncio.StreamReader()
        if self._preload:
            self.reader.feed_data(self._preload)
        return self.reader, self.writer


def install_port(
    monkeypatch: pytest.MonkeyPatch,
    reply_for: Callable[[str], bytes | None],
    *,
    preload: bytes = b"",
) -> FakePort:
    """Patch open_serial_connection so the transport talks to a FakePort."""
    port = FakePort(reply_for, preload)
    monkeypatch.setattr("smart_serial.transport.serial_asyncio.open_serial_connection", port.open)
    return port


def echo_device(command: str) -> bytes:
    """A device that answers 'get k' with 'k=1' + CRLF + prompt."""
    return f"\r\n{command.split()[-1]}=1\r\n>".encode()


def test_exchange_returns_the_text_before_the_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    port = install_port(monkeypatch, echo_device)

    async def scenario() -> str:
        transport = SerialTransport("fake", FAST)
        await transport.connect()
        return await transport.exchange("get brightness")

    assert asyncio.run(scenario()) == "\r\nbrightness=1\r\n"
    assert b"".join(port.writer.writes) == b"get brightness\r"


def test_writes_are_paced_one_byte_at_a_time(monkeypatch: pytest.MonkeyPatch) -> None:
    port = install_port(monkeypatch, echo_device)

    async def scenario() -> None:
        transport = SerialTransport("fake", FAST)
        await transport.connect()
        await transport.exchange("on")

    asyncio.run(scenario())
    assert port.writer.writes == [b"o", b"n", b"\r"]


def test_pacing_delay_is_applied_between_characters(monkeypatch: pytest.MonkeyPatch) -> None:
    install_port(monkeypatch, echo_device)
    sleeps: list[float] = []
    real_sleep = asyncio.sleep

    async def spy_sleep(delay: float) -> None:
        sleeps.append(delay)
        await real_sleep(0)

    monkeypatch.setattr("smart_serial.transport.asyncio.sleep", spy_sleep)
    settings = SerialSettings(inter_character_delay=0.01, response_timeout=0.2, drain_timeout=0.01)

    async def scenario() -> None:
        transport = SerialTransport("fake", settings)
        await transport.connect()
        await transport.exchange("on")  # 'o', 'n', '\r' -> 2 gaps

    asyncio.run(scenario())
    assert sleeps == [0.01, 0.01]


def test_exchange_before_connect_raises() -> None:
    with pytest.raises(ConnectionNotEstablishedError):
        asyncio.run(SerialTransport("fake", FAST).exchange("on"))


def test_connect_is_idempotent_and_resets_the_input_buffer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = install_port(monkeypatch, echo_device)

    async def scenario() -> None:
        transport = SerialTransport("fake", FAST)
        await transport.connect()
        await transport.connect()
        assert transport.is_connected

    asyncio.run(scenario())
    assert port.writer.transport.serial.input_resets == 1


def test_connect_failure_is_a_library_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(**_: object) -> None:
        raise FileNotFoundError("No such file: /dev/ttyNOPE")

    monkeypatch.setattr("smart_serial.transport.serial_asyncio.open_serial_connection", boom)
    with pytest.raises(ConnectionFailedError, match="/dev/ttyNOPE"):
        asyncio.run(SerialTransport("/dev/ttyNOPE", FAST).connect())


def test_stale_prompt_is_discarded_before_the_first_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A '>' left over from before we connected must not be mistaken for the reply."""
    install_port(monkeypatch, echo_device, preload=b">")

    async def scenario() -> str:
        transport = SerialTransport("fake", FAST)
        await transport.connect()
        return await transport.exchange("get volume")

    assert asyncio.run(scenario()) == "\r\nvolume=1\r\n"


def _count_drains(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []
    original = SerialTransport._drain_stale

    async def counting(self: SerialTransport, reader: asyncio.StreamReader) -> None:
        calls.append(1)
        await original(self, reader)

    monkeypatch.setattr(SerialTransport, "_drain_stale", counting)
    return calls


def test_no_drain_delay_in_the_steady_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drain after connect only; successful exchanges consume their own prompt."""
    install_port(monkeypatch, echo_device)
    drains = _count_drains(monkeypatch)

    async def scenario() -> None:
        transport = SerialTransport("fake", FAST)
        await transport.connect()
        for _ in range(5):
            await transport.exchange("get volume")

    asyncio.run(scenario())
    assert len(drains) == 1


def test_timeout_raises_and_triggers_a_drain_before_the_next_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answer = False

    def device(command: str) -> bytes | None:
        return echo_device(command) if answer else None

    install_port(monkeypatch, device)
    drains = _count_drains(monkeypatch)

    async def scenario() -> None:
        nonlocal answer
        transport = SerialTransport("fake", FAST)
        await transport.connect()
        with pytest.raises(SerialTimeoutError) as excinfo:
            await transport.exchange("get volume")
        assert excinfo.value.command == "get volume"
        assert transport.is_connected  # a timeout is not a disconnect
        answer = True
        assert await transport.exchange("get volume") == "\r\nvolume=1\r\n"

    asyncio.run(scenario())
    assert len(drains) == 2  # once after connect, once after the failed exchange


def test_eof_means_connection_lost_not_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unplugged adapter shows up as EOF; retrying it as a timeout would be pointless."""
    port = install_port(monkeypatch, lambda _command: None)

    async def scenario() -> None:
        transport = SerialTransport("fake", FAST)
        await transport.connect()
        assert port.reader is not None
        port.reader.feed_eof()
        with pytest.raises(ConnectionLostError):
            await transport.exchange("get volume")
        assert not transport.is_connected
        with pytest.raises(ConnectionNotEstablishedError):
            await transport.exchange("get volume")

    asyncio.run(scenario())


def test_concurrent_exchanges_never_interleave(monkeypatch: pytest.MonkeyPatch) -> None:
    port = install_port(monkeypatch, echo_device)

    async def scenario() -> list[str]:
        transport = SerialTransport("fake", FAST)
        await transport.connect()
        return list(
            await asyncio.gather(
                transport.exchange("get a"),
                transport.exchange("get b"),
                transport.exchange("get c"),
            )
        )

    replies = asyncio.run(scenario())
    assert [r.strip() for r in replies] == ["a=1", "b=1", "c=1"]
    assert b"".join(port.writer.writes) == b"get a\rget b\rget c\r"


def test_disconnect_is_safe_when_never_connected_and_closes_the_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = install_port(monkeypatch, echo_device)

    async def scenario() -> None:
        transport = SerialTransport("fake", FAST)
        await transport.disconnect()  # never connected: no error
        async with transport:
            assert transport.is_connected
        assert not transport.is_connected

    asyncio.run(scenario())
    assert port.writer.closed
