"""Exceptions raised by this library.

Hierarchy::

    SmartSerialError
    ├── ConnectionNotEstablishedError   # command sent before connect()
    ├── ConnectionFailedError           # the port could not be opened
    ├── ConnectionLostError             # the link dropped mid-exchange
    ├── SerialTimeoutError              # no reply within the timeout
    └── CommandError                    # the device replied, but not with success
        ├── CommandRejectedError        # "invalid cmd=..." echoed back
        │   └── DeviceIdleError         # ...and the device is idle/off
        └── UnexpectedResponseError     # reply could not be parsed
"""

from __future__ import annotations


class SmartSerialError(Exception):
    """Base class for every exception raised by this library."""


class ConnectionNotEstablishedError(SmartSerialError):
    """Raised when a command is sent before :meth:`connect` succeeded."""

    port: str

    def __init__(self, port: str) -> None:
        super().__init__(f"Not connected to {port!r}. Call connect() first.")
        self.port = port


class ConnectionFailedError(SmartSerialError):
    """Raised when the serial port could not be opened."""

    port: str
    reason: str

    def __init__(self, port: str, reason: str) -> None:
        super().__init__(f"Could not open {port!r}: {reason}")
        self.port = port
        self.reason = reason


class ConnectionLostError(SmartSerialError):
    """Raised when the connection drops mid-exchange (e.g. USB adapter unplugged).

    The transport marks itself disconnected before raising this, so callers
    should :meth:`~smart_serial.Device.connect` again before retrying.
    """

    port: str

    def __init__(self, port: str, reason: str = "connection closed") -> None:
        super().__init__(f"Lost connection to {port!r}: {reason}")
        self.port = port


class SerialTimeoutError(SmartSerialError):
    """Raised when a device doesn't respond within the configured timeout."""

    port: str
    command: str

    def __init__(self, port: str, command: str) -> None:
        super().__init__(f"Timed out waiting for a response to {command!r} on {port!r}.")
        self.port = port
        self.command = command


class CommandError(SmartSerialError):
    """Raised when a device reports that a command failed, or replies unintelligibly."""

    command: str
    response: str

    def __init__(self, command: str, response: str, message: str | None = None) -> None:
        super().__init__(message or f"Command {command!r} failed: {response!r}")
        self.command = command
        self.response = response


class CommandRejectedError(CommandError):
    """Raised when the device answers ``invalid cmd=<the command we sent>``."""


class DeviceIdleError(CommandRejectedError):
    """Raised when a command was rejected *and* the device reports that it is idle/off."""

    def __init__(self, command: str, response: str) -> None:
        super().__init__(
            command,
            response,
            f"Command {command!r} is not available while the device is idle/off: {response!r}",
        )


class UnexpectedResponseError(CommandError):
    """Raised when the device replied, but the reply could not be parsed."""

    def __init__(self, command: str, response: str, reason: str | None = None) -> None:
        detail = f" ({reason})" if reason else ""
        super().__init__(
            command, response, f"Unexpected reply to {command!r}: {response!r}{detail}"
        )
