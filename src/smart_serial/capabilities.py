"""Small, device-independent capability protocols.

A generic consumer (for example a Home Assistant integration) can ask what a
device supports with ``isinstance`` instead of calling methods and catching
"not supported" errors::

    if isinstance(device, PowerControl):
        await device.turn_on()

The protocols are structural: a driver satisfies one simply by having the
methods; it does not need to inherit from it. Only add a protocol here once
two devices actually share the feature.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PowerControl(Protocol):
    """Turn a device on and off, and report whether it is on.

    Unlike driver-specific power methods, these have plain semantics:
    ``turn_off()`` returns once the device has been told to shut down, with any
    confirmation steps the hardware requires already handled.
    """

    async def turn_on(self) -> None: ...

    async def turn_off(self) -> None: ...

    async def is_on(self) -> bool:
        """``True`` if the device is on or in the process of powering on."""
        ...
