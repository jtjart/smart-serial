from __future__ import annotations

import asyncio
import dataclasses
from typing import TYPE_CHECKING, assert_type

from smart_serial import PowerControl, SerialSettings, SerialTransport, SmartUX60

if TYPE_CHECKING:
    from conftest import FakeTransport


def test_create_returns_the_concrete_class() -> None:
    projector = SmartUX60.create("/dev/ttyUSB0")
    assert_type(projector, SmartUX60)  # this is what gives you completion
    assert isinstance(projector, SmartUX60)
    assert isinstance(projector.transport, SerialTransport)
    assert projector.transport.port == "/dev/ttyUSB0"
    assert projector.transport.settings.baudrate == 19200


def test_create_accepts_settings_override() -> None:
    settings = dataclasses.replace(SmartUX60.serial_settings, baudrate=9600)
    projector = SmartUX60.create("COM3", settings)
    assert isinstance(projector.transport, SerialTransport)
    assert projector.transport.settings.baudrate == 9600
    assert SmartUX60.serial_settings.baudrate == 19200  # class default untouched


def test_serial_settings_are_frozen() -> None:
    settings = SerialSettings()
    try:
        settings.baudrate = 1  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("SerialSettings should be immutable")


def test_async_context_manager_returns_the_concrete_class(fake: FakeTransport) -> None:
    async def scenario() -> None:
        projector = SmartUX60(fake)
        async with projector as entered:
            assert_type(entered, SmartUX60)
            assert entered is projector
            assert projector.is_connected
        assert not projector.is_connected

    asyncio.run(scenario())
    assert (fake.connect_calls, fake.disconnect_calls) == (1, 1)


def test_metadata() -> None:
    assert SmartUX60.vendor == "SMART Technologies"
    assert SmartUX60.model == "UX60"


def test_ux60_is_a_power_control(projector: SmartUX60) -> None:
    assert isinstance(projector, PowerControl)
    control: PowerControl = projector  # static conformance check under mypy
    assert control is projector
