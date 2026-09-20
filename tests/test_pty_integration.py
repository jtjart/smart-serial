"""End-to-end: the real stack (pyserial + serial_asyncio_fast) against an emulated projector.

A pseudo-terminal pair stands in for the RS-232 cable; a thread on the far end
behaves like the UX60's console (CR-terminated commands, replies followed by a
``>`` prompt). POSIX only.
"""

from __future__ import annotations

import asyncio
import os
import threading
from collections.abc import Iterator

import pytest

from smart_serial import CommandRejectedError, PowerControl, SerialTransport, SmartUX60, Source
from smart_serial.devices.ux60 import DisplayMode, PowerState

if os.name != "posix":
    pytest.skip("needs a POSIX pseudo-terminal", allow_module_level=True)

import pty
import tty


class EmulatedProjector(threading.Thread):
    """Just enough of the UX60 console to exercise the driver."""

    def __init__(self, fd: int) -> None:
        super().__init__(daemon=True)
        self.fd = fd
        self.received: list[str] = []
        self.state = "Idle"
        self.values = {"brightness": "45", "displaymode": "DarkRoom", "input": "hdmi1"}
        self._stopping = threading.Event()

    def run(self) -> None:
        os.write(self.fd, b">")  # a stale prompt, as some adapters leave behind
        buffer = b""
        while not self._stopping.is_set():
            try:
                chunk = os.read(self.fd, 64)
            except OSError:
                return
            buffer += chunk
            while b"\r" in buffer:
                line, buffer = buffer.split(b"\r", 1)
                command = line.decode().strip()
                self.received.append(command)
                os.write(self.fd, f"\r\n{self.reply(command)}\r\n>".encode())

    def reply(self, command: str) -> str:
        if command == "on":
            self.state = "Powering"
        elif command == "off":
            self.state = "Confirm off" if self.state == "On" else "Cooling"
            if self.state == "Confirm off":
                return "powerstate=Confirm off"
        elif command == "off now":
            self.state = "Cooling"
        elif command == "get powerstate":
            pass
        elif command.startswith("get "):
            key = command[4:]
            return f"{key}={self.values[key]}" if key in self.values else f"invalid cmd={command}"
        elif command.startswith("set ") and "=" in command:
            key, value = command[4:].split("=", 1)
            self.values[key] = value
            return f"{key}={value}"
        else:
            return f"invalid cmd={command}"
        return f"powerstate={self.state}"

    def stop(self) -> None:
        self._stopping.set()


@pytest.fixture
def port() -> Iterator[tuple[str, EmulatedProjector]]:
    master, slave = pty.openpty()
    tty.setraw(slave)  # a serial line does not echo
    emulator = EmulatedProjector(master)
    emulator.state = "On"
    emulator.start()
    yield os.ttyname(slave), emulator
    emulator.stop()
    os.close(slave)
    os.close(master)


def test_full_stack_round_trip(port: tuple[str, EmulatedProjector]) -> None:
    path, emulator = port

    async def scenario() -> None:
        projector = SmartUX60.create(path)
        assert isinstance(projector, PowerControl)
        async with projector:
            assert await projector.brightness.get() == 45  # the stale '>' was drained
            assert await projector.brightness.set(70) == 70
            assert await projector.display_mode.get() is DisplayMode.DARKROOM
            assert await projector.select_input("HDMI 2") == Source("hdmi2")
            assert await projector.get_power_state() is PowerState.ON
            await projector.turn_off()  # answers "Confirm off"
            assert await projector.get_power_state() is PowerState.COOLING
            assert await projector.is_on() is False
            # Rejected while not idle: reported as a rejection, not mislabelled "idle".
            with pytest.raises(CommandRejectedError, match="get volume"):
                await projector.volume.get()

    asyncio.run(scenario())
    assert emulator.received == [
        "get brightness",
        "set brightness=70",
        "get displaymode",
        "set input=hdmi2",
        "get powerstate",
        "off now",
        "get powerstate",
        "get powerstate",
        "get volume",
        "get powerstate",  # asked to tell "idle" apart from "unsupported right now"
    ]


def test_only_the_first_command_pays_for_draining(
    port: tuple[str, EmulatedProjector], monkeypatch: pytest.MonkeyPatch
) -> None:
    path, _ = port
    drains: list[int] = []
    original = SerialTransport._drain_stale

    async def counting(self: SerialTransport, reader: asyncio.StreamReader) -> None:
        drains.append(1)
        await original(self, reader)

    monkeypatch.setattr(SerialTransport, "_drain_stale", counting)

    async def scenario() -> None:
        async with SmartUX60.create(path) as projector:
            for _ in range(5):
                await projector.brightness.get()

    asyncio.run(scenario())
    assert len(drains) == 1
