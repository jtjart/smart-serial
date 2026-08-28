from __future__ import annotations

import pytest

from smart_serial.device import Device
from smart_serial.exceptions import UnsupportedDeviceError
from smart_serial.registry import available_devices, get_device_class, register


def test_builtin_ux60_is_registered() -> None:
    assert "smart:ux60" in available_devices()


def test_unknown_device_raises() -> None:
    with pytest.raises(UnsupportedDeviceError):
        get_device_class("nope", "nope")


def test_register_custom_driver_is_discoverable_case_insensitively() -> None:
    @register
    class _FakeDevice(Device):
        vendor = "acme"
        model = "widget"

        async def power_on(self) -> str:
            return "on"

        async def power_off(self) -> str:
            return "off"

        async def get_power_state(self) -> str:
            return "on"

    assert get_device_class("ACME", "Widget") is _FakeDevice
