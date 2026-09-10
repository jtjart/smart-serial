"""smart-serial: asyncio control of SMART Technologies AV devices over RS-232.

The library ships with a driver for the SMART UX60 projector and is built
so additional vendors/models can be added without touching this package's
internals -- see :mod:`smart_serial.registry` for how the driver lookup
works, and ``src/smart_serial/devices/smart/ux60.py`` for an example
driver to copy when adding a new model.
"""

from __future__ import annotations

__version__ = "0.1.0"

# Importing this subpackage registers every driver that ships with the
# library. Importing happens here so `import smart_serial` is all a user
# needs before calling create_device(). Third-party drivers register
# themselves the same way, or lazily via entry points -- see registry.py.
from . import devices  # noqa: F401
from .device import Device
from .exceptions import (
    CommandError,
    ConnectionNotEstablishedError,
    DeviceIdleError,
    SerialTimeoutError,
    SmartSerialError,
    UnsupportedDeviceError,
)
from .registry import available_devices, create_device, get_device_class, register
from .transport import SerialTransport

__all__ = [
    "CommandError",
    "ConnectionNotEstablishedError",
    "Device",
    "DeviceIdleError",
    "SerialTimeoutError",
    "SerialTransport",
    "SmartSerialError",
    "UnsupportedDeviceError",
    "__version__",
    "available_devices",
    "create_device",
    "get_device_class",
    "register",
]
