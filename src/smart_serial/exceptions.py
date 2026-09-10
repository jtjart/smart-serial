"""Exceptions raised by this library."""

from __future__ import annotations


class SmartSerialError(Exception):
    """Base class for every exception raised by this library."""


class ConnectionNotEstablishedError(SmartSerialError):
    """Raised when a command is sent before :meth:`connect` succeeded."""

    def __init__(self, port: str) -> None:
        super().__init__(f"Not connected to {port!r}. Call connect() first.")
        self.port = port


class SerialTimeoutError(SmartSerialError):
    """Raised when a device doesn't respond within the configured timeout."""

    def __init__(self, port: str, command: str) -> None:
        super().__init__(f"Timed out waiting for a response to {command!r} on {port!r}.")
        self.port = port
        self.command = command


class CommandError(SmartSerialError):
    """Raised when a device reports that a command failed, or an unparsable reply."""

    def __init__(self, command: str, response: str) -> None:
        super().__init__(f"Command {command!r} failed: {response!r}")
        self.command = command
        self.response = response


class DeviceIdleError(CommandError):
    """Raised when the device accepts the command but rejects it because it is idle/off."""

    def __init__(self, command: str, response: str) -> None:
        super().__init__(command, response)
        self.message = (
            f"Command {command!r} is not available while the device is idle/off: {response!r}"
        )


class UnsupportedDeviceError(SmartSerialError):
    """Raised when no driver is registered for a requested vendor/model pair."""

    def __init__(self, vendor: str, model: str) -> None:
        super().__init__(
            f"No driver registered for device {vendor!r}:{model!r}. "
            "Call smart_serial.available_devices() to see what's registered."
        )
        self.vendor = vendor
        self.model = model
