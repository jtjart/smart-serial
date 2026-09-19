"""The :class:`Source` value object: a video input identifier."""

from __future__ import annotations

import re
from dataclasses import dataclass

_DISPLAY_NAMES: dict[str, str] = {
    "component": "Component",
    "composite": "Composite",
    "displayport": "DisplayPort",
    "dvi": "DVI",
    "hdmi": "HDMI",
    "s-video": "S-Video",
    "usb": "USB",
    "vga": "VGA",
}

_NAME_AND_NUMBER = re.compile(r"(?P<name>\D+?)(?P<number>\d+)?")


@dataclass(frozen=True, slots=True)
class Source:
    """A video input, identified by the name the device uses on the wire (e.g. ``"vga1"``).

    The value is normalized on construction (whitespace removed, lower-cased), so
    ``Source("VGA 1") == Source("vga1")``. Instances are immutable and hashable.

    ``Source`` is deliberately an open value object rather than an enum: the set of
    inputs differs per model and firmware. Ask the device via
    ``SmartUX60.get_video_inputs()`` for what is actually available.
    """

    value: str

    def __post_init__(self) -> None:
        normalized = "".join(self.value.split()).lower()
        if not normalized:
            raise ValueError("Source must not be empty")
        object.__setattr__(self, "value", normalized)

    @classmethod
    def coerce(cls, value: Source | str) -> Source:
        """Return ``value`` unchanged if it is a :class:`Source`, else build one from a string."""
        return value if isinstance(value, Source) else cls(value)

    @property
    def display_name(self) -> str:
        """A human-readable name suitable for display, e.g. ``"VGA 1"``."""
        match = _NAME_AND_NUMBER.fullmatch(self.value)
        if match is None:
            return self.value
        name, number = match["name"], match["number"]
        label = _DISPLAY_NAMES.get(name, name.title())
        return f"{label} {number}" if number else label

    def __str__(self) -> str:
        return self.value
