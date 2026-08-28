"""Abstract base class every device driver in this library builds on."""

from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType
from typing import ClassVar

from .transport import SerialTransport


class Device(ABC):
    """Base class for a serial-controlled AV device.

    Subclasses implement the command set for one specific model. Each
    subclass sets :attr:`vendor` and :attr:`model` and registers itself
    with :func:`smart_serial.registry.register` (usually via the
    ``@register`` decorator) so it can be found by
    :func:`smart_serial.registry.create_device`.

    See ``src/smart_serial/devices/smart/ux60.py`` for a complete example
    to copy when adding support for a new model.
    """

    #: Short, lowercase identifiers used as the registry lookup key, e.g.
    #: ``vendor = "smart"``, ``model = "ux60"``.
    vendor: ClassVar[str]
    model: ClassVar[str]

    #: Serial parameters this model expects out of the box. Subclasses
    #: override whichever of these differ from the RS-232 default (9600
    #: baud, 8N1) for their hardware.
    default_baudrate: ClassVar[int] = 9600

    def __init__(self, transport: SerialTransport) -> None:
        self._transport = transport

    @property
    def transport(self) -> SerialTransport:
        return self._transport

    async def connect(self) -> None:
        await self._transport.connect()

    async def disconnect(self) -> None:
        await self._transport.disconnect()

    async def __aenter__(self) -> Device:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.disconnect()

    @classmethod
    def create(cls, port: str, **transport_kwargs: object) -> Device:
        """Convenience constructor that also builds the matching transport.

        Most callers should go through
        :func:`smart_serial.registry.create_device` instead, which also
        looks the class up by vendor/model; this exists for when you
        already have the concrete class in hand.
        """
        transport_kwargs.setdefault("baudrate", cls.default_baudrate)
        transport = SerialTransport(port, **transport_kwargs)  # type: ignore[arg-type]
        return cls(transport)

    # --- Capabilities every device driver is expected to implement -----
    # Kept deliberately small so that adding a new, very different model
    # (e.g. an audio matrix switcher) doesn't force it to implement
    # projector-specific concepts like lamp hours or input switching.
    # Add capability-specific mixins/ABCs alongside this one as the
    # library grows, rather than growing this base class indefinitely.

    @abstractmethod
    async def power_on(self) -> str:
        """Power the device on. Returns the driver-specific resulting state."""

    @abstractmethod
    async def power_off(self) -> str:
        """Power the device off. Returns the driver-specific resulting state."""

    @abstractmethod
    async def get_power_state(self) -> str:
        """Return the device's raw, driver-specific power state string."""
