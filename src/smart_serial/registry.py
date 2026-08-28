"""Pluggable registry mapping ``(vendor, model)`` to a :class:`Device` subclass.

Built-in drivers register themselves with the :func:`register` decorator
when their module is imported (see ``smart_serial/devices/__init__.py``).

Third-party packages can add support for additional models *without*
depending on, or modifying, this package's source at all, by exposing an
entry point in the ``smart_serial.devices`` group. For example, a
separate ``acme-smart-serial`` package could ship this in its own
``pyproject.toml``::

    [project.entry-points."smart_serial.devices"]
    "acme:projector-9000" = "acme_smart_serial.driver:AcmeProjector9000"

Once that package is installed alongside ``smart-serial``, it's
automatically picked up -- no changes needed here.
"""

from __future__ import annotations

from importlib import metadata as importlib_metadata

from .device import Device
from .exceptions import UnsupportedDeviceError

_ENTRY_POINT_GROUP = "smart_serial.devices"
_registry: dict[str, type[Device]] = {}
_entry_points_loaded = False


def _key(vendor: str, model: str) -> str:
    return f"{vendor.strip().lower()}:{model.strip().lower()}"


def register(device_cls: type[Device]) -> type[Device]:
    """Class decorator that registers a :class:`Device` subclass.

    Usage::

        @register
        class MyProjector(Device):
            vendor = "acme"
            model = "projector-9000"
            ...
    """
    _registry[_key(device_cls.vendor, device_cls.model)] = device_cls
    return device_cls


def _load_entry_points() -> None:
    """Discover and import third-party drivers exactly once per process."""
    global _entry_points_loaded
    if _entry_points_loaded:
        return
    for entry_point in importlib_metadata.entry_points(group=_ENTRY_POINT_GROUP):
        # Loading the entry point imports its module, which runs the
        # @register decorator on the class it points to. We don't need
        # the returned object itself.
        entry_point.load()
    _entry_points_loaded = True


def available_devices() -> list[str]:
    """Return the sorted ``"vendor:model"`` keys of every known driver."""
    _load_entry_points()
    return sorted(_registry)


def get_device_class(vendor: str, model: str) -> type[Device]:
    """Look up a registered driver class by vendor and model."""
    _load_entry_points()
    try:
        return _registry[_key(vendor, model)]
    except KeyError as exc:
        raise UnsupportedDeviceError(vendor, model) from exc


def create_device(vendor: str, model: str, port: str, **transport_kwargs: object) -> Device:
    """Look up the driver for ``vendor``/``model`` and build it for ``port``.

    ``transport_kwargs`` are forwarded to :class:`~smart_serial.transport.SerialTransport`
    (e.g. ``baudrate=19200``), overriding the driver's defaults.
    """
    device_cls = get_device_class(vendor, model)
    return device_cls.create(port, **transport_kwargs)
