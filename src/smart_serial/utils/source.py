from __future__ import annotations

import re

_DISPLAY_NAMES: dict[str, str] = {
    "component": "Component",
    "composite": "Composite",
    "dvi": "DVI",
    "hdmi": "HDMI",
    "s-video": "S-Video",
    "vga": "VGA",
}


class Source:
    """A projector source."""

    def __init__(self, value: str) -> None:
        self.value: str = value.strip().lower()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Source):
            return NotImplemented

        return self.value == other.value

    def __hash__(self) -> int:
        return hash(self.value)

    @property
    def display_name(self) -> str:
        """Return a human-readable name suitable for display."""
        match = re.fullmatch(r"(.+?)(\d+)?", self.value)

        if match is None:
            return self.value

        name, number = match.groups()

        display_name = _DISPLAY_NAMES.get(name, name.title())

        if number is not None:
            return f"{display_name} {number}"

        return display_name

    def __str__(self) -> str:
        return self.value
