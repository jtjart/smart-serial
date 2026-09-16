"""smart-serial: asyncio control of SMART Technologies AV devices over RS-232."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

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

try:
    __version__ = version("smart-serial")
except PackageNotFoundError:
    # Fallback when the package is used locally without being installed
    __version__ = "unknown"

__all__ = [
    "CommandError",
    "ConnectionNotEstablishedError",
    "Device",
    "DeviceIdleError",
    "SerialTimeoutError",
    "SerialTransport",
    "SmartSerialError",
    "SmartUX60",
]
