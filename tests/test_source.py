from __future__ import annotations

import dataclasses

import pytest

from smart_serial import Source


def test_normalizes_case_and_whitespace() -> None:
    assert Source("VGA 1") == Source("vga1") == Source("  Vga1 ")
    assert Source("VGA 1").value == "vga1"


def test_is_hashable_and_usable_in_sets() -> None:
    assert {Source("HDMI1"), Source("hdmi1"), Source("hdmi2")} == {Source("hdmi1"), Source("hdmi2")}


def test_is_immutable() -> None:
    source = Source("hdmi1")
    with pytest.raises(dataclasses.FrozenInstanceError):
        source.value = "vga1"  # type: ignore[misc]


def test_rejects_empty() -> None:
    for text in ("", "   "):
        with pytest.raises(ValueError, match="empty"):
            Source(text)


def test_str_and_repr_are_useful() -> None:
    assert str(Source("hdmi1")) == "hdmi1"
    assert repr(Source("hdmi1")) == "Source(value='hdmi1')"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("vga1", "VGA 1"),
        ("VGA 1", "VGA 1"),  # GUI-style spelling no longer yields "Vga  1"
        ("hdmi", "HDMI"),
        ("hdmi2", "HDMI 2"),
        ("usb2", "USB 2"),
        ("s-video", "S-Video"),
        ("component1", "Component 1"),
        ("wireless", "Wireless"),  # unknown names fall back to title case
        ("42", "42"),  # nothing sensible to do with a bare number
    ],
)
def test_display_name(value: str, expected: str) -> None:
    assert Source(value).display_name == expected


def test_coerce() -> None:
    source = Source("hdmi1")
    assert Source.coerce(source) is source
    assert Source.coerce("HDMI 1") == source
