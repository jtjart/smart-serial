"""Abstract base class every device driver in this library builds on."""

from __future__ import annotations

from abc import ABC
from types import TracebackType
from typing import ClassVar, Self

from .transport import SerialSettings, SerialTransport, Transport


class Device(ABC):
    """Base class for a serial-controlled AV device.

    A ``Device`` owns the connection lifecycle and identifies itself
    (:attr:`vendor`, :attr:`model`, :attr:`serial_settings`). Everything a device
    can *do* is exposed by the concrete class, and -- where features are shared
    across devices -- by the small protocols in :mod:`smart_serial.capabilities`.
    """

    vendor: ClassVar[str]
    model: ClassVar[str]

    #: Line settings used by :meth:`create`. Concrete drivers override this.
    serial_settings: ClassVar[SerialSettings] = SerialSettings()

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    @classmethod
    def create(cls, port: str, settings: SerialSettings | None = None) -> Self:
        """Build a device on a new :class:`SerialTransport` for ``port``.

        Returns the concrete subclass, so ``SmartUX60.create(...)`` is typed as
        ``SmartUX60``. Pass ``settings`` to override :attr:`serial_settings`
        (e.g. ``dataclasses.replace(SmartUX60.serial_settings, baudrate=9600)``).
        The port is not opened until :meth:`connect` (or ``async with``).
        """
        return cls(SerialTransport(port, settings if settings is not None else cls.serial_settings))

    @property
    def transport(self) -> Transport:
        return self._transport

    @property
    def is_connected(self) -> bool:
        return self._transport.is_connected

    async def connect(self) -> None:
        await self._transport.connect()

    async def disconnect(self) -> None:
        await self._transport.disconnect()

    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.disconnect()
