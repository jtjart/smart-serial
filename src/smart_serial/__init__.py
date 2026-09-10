"""smart-serial: asyncio control of SMART Technologies AV devices over RS-232."""

from __future__ import annotations

from .device import Device
from .devices.smart.ux60 import SmartUX60
from .exceptions import (
    CommandError,
    ConnectionNotEstablishedError,
    DeviceIdleError,
    SerialTimeoutError,
    SmartSerialError,
)
from .transport import SerialTransport

__version__ = "0.1.0"

__all__ = [
    "CommandError",
    "ConnectionNotEstablishedError",
    "Device",
    "DeviceIdleError",
    "SerialTimeoutError",
    "SerialTransport",
    "SmartSerialError",
    "SmartUX60",
    "__version__",
]
