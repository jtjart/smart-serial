"""Built-in device drivers.

New device support is added by creating a concrete ``Device`` subclass in
this package and importing it here so callers can use an explicit import
from the public module path.
"""

from __future__ import annotations

from .smart.ux60 import SmartUX60

__all__ = ["SmartUX60"]
