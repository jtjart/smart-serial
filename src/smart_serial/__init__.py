"""smart-serial: asyncio control of SMART Technologies AV devices over RS-232."""

from __future__ import annotations

from ._version import __version__
from .capabilities import PowerControl
from .device import Device
from .devices.base import SmartDevice
from .devices.ux60 import SmartUX60
from .exceptions import (
    CommandError,
    CommandRejectedError,
    ConnectionFailedError,
    ConnectionLostError,
    ConnectionNotEstablishedError,
    DeviceIdleError,
    SerialTimeoutError,
    SmartSerialError,
    UnexpectedResponseError,
)
from .source import Source
from .transport import SerialSettings, SerialTransport, Transport

__all__ = [
    "CommandError",
    "CommandRejectedError",
    "ConnectionFailedError",
    "ConnectionLostError",
    "ConnectionNotEstablishedError",
    "Device",
    "DeviceIdleError",
    "PowerControl",
    "SerialSettings",
    "SerialTimeoutError",
    "SerialTransport",
    "SmartDevice",
    "SmartSerialError",
    "SmartUX60",
    "Source",
    "Transport",
    "UnexpectedResponseError",
    "__version__",
]
