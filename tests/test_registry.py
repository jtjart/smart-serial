from __future__ import annotations

import smart_serial
from smart_serial.devices.smart.ux60 import SmartUX60


def test_explicit_device_import_is_the_public_api() -> None:
    assert smart_serial.SmartUX60 is SmartUX60
    assert not hasattr(smart_serial, "create_device")
    assert not hasattr(smart_serial, "available_devices")
    assert not hasattr(smart_serial, "register")
