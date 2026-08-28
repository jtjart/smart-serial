"""Built-in device drivers.

Importing this subpackage registers every driver that ships with the
library, by importing each driver module below (each module registers
itself via the ``@register`` decorator as a side effect of being
imported). This happens automatically when you ``import smart_serial``.

To add support for a new model that lives *inside* this package (as
opposed to a separate, third-party plugin package -- see
``smart_serial.registry`` for that route):

1. Create ``smart_serial/devices/<vendor>/<model>.py`` implementing a
   ``Device`` subclass, following ``devices/smart/ux60.py`` as a template.
2. Import it below.
3. Optionally add a matching ``[project.entry-points."smart_serial.devices"]``
   line in ``pyproject.toml`` so it's also discoverable by tools that
   inspect entry points without importing ``smart_serial`` directly.
"""

from __future__ import annotations

from .smart.ux60 import SmartUX60

__all__ = ["SmartUX60"]
