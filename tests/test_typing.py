"""Static-typing guarantees, enforced by running ``mypy src tests``.

Each ``# type: ignore[...]`` below asserts that mypy *rejects* the line. With
``strict = true`` (``warn_unused_ignores``), the ignore itself becomes an error if
the line ever starts type-checking -- i.e. if the typing regresses.
"""

from __future__ import annotations

import inspect

from smart_serial import SmartUX60


async def _misuse_is_rejected(projector: SmartUX60) -> None:
    await projector.display_mode.set("darkroom")  # type: ignore[arg-type]
    await projector.display_mode.adjust(1)  # type: ignore[attr-defined]
    await projector.brightness.set("5")  # type: ignore[arg-type]
    await projector.serial_number.set("x")  # type: ignore[attr-defined]
    await projector.serial_number.adjust(1)  # type: ignore[attr-defined]
    await projector.zoom.adjust(1)  # type: ignore[attr-defined]  # not documented as adjustable
    await projector.no_such_setting.get()  # type: ignore[attr-defined]


def test_the_static_checks_are_collected_but_never_run() -> None:
    assert inspect.iscoroutinefunction(_misuse_is_rejected)
