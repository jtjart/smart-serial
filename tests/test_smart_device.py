"""The protocol layer: reply selection, retry policy, rejection handling."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from smart_serial import (
    CommandRejectedError,
    DeviceIdleError,
    SerialTimeoutError,
    SmartUX60,
)
from smart_serial.devices.base import select_reply

if TYPE_CHECKING:
    from conftest import FakeTransport


def timeout(command: str = "x") -> SerialTimeoutError:
    return SerialTimeoutError("fake", command)


# -------------------------------------------------------------------- reply selection


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("brightness=45", "brightness=45"),
        ("\r\nbrightness=45\r\n", "brightness=45"),
        ("noise\r\nbrightness=45\r\n", "brightness=45"),
        ("brightness=45\r\ntrailing junk\r\n", "brightness=45"),  # prefers the key=value line
        ("Powering", "Powering"),  # no '=': last non-empty line
        ("   \r\n  ", ""),
        ("", ""),
    ],
)
def test_select_reply(text: str, expected: str) -> None:
    assert select_reply(text) == expected


def test_multiline_transport_text_is_handled(projector: SmartUX60, fake: FakeTransport) -> None:
    fake.queue("\r\nget brightness\r\nbrightness=45\r\n")
    assert asyncio.run(projector.get_value("brightness")) == "45"


# ------------------------------------------------------------------------ retry policy


def test_get_is_retried_after_a_timeout(projector: SmartUX60, fake: FakeTransport) -> None:
    fake.queue(timeout(), "x=1")
    assert asyncio.run(projector.get_value("x")) == "1"
    assert fake.sent == ["get x", "get x"]


def test_absolute_set_is_retried_after_a_timeout(projector: SmartUX60, fake: FakeTransport) -> None:
    fake.queue(timeout(), "volume=5")
    assert asyncio.run(projector.set_value("volume", "5")) == "5"
    assert fake.sent == ["set volume=5", "set volume=5"]


def test_retries_are_bounded(projector: SmartUX60, fake: FakeTransport) -> None:
    fake.queue(timeout(), timeout(), timeout())
    with pytest.raises(SerialTimeoutError):
        asyncio.run(projector.get_value("x"))
    assert len(fake.sent) == 3


def test_relative_adjustment_is_never_resent_after_a_timeout(
    projector: SmartUX60, fake: FakeTransport
) -> None:
    """A timeout is ambiguous; the first '+5' may have applied. Sending again would double it."""
    fake.queue(timeout(), "volume=10")
    with pytest.raises(SerialTimeoutError):
        asyncio.run(projector.adjust_value("volume", 5))
    assert fake.sent == ["set volume+5"]


def test_off_is_never_resent_after_a_timeout(projector: SmartUX60, fake: FakeTransport) -> None:
    """Re-sending 'off' would be read as the shutdown confirmation nobody asked for."""
    fake.queue(timeout(), "powerstate=Cooling")
    with pytest.raises(SerialTimeoutError):
        asyncio.run(projector.power_off())
    assert fake.sent == ["off"]


def test_on_is_retried_after_a_timeout(projector: SmartUX60, fake: FakeTransport) -> None:
    fake.queue(timeout(), "powerstate=Powering")
    asyncio.run(projector.power_on())
    assert fake.sent == ["on", "on"]


def test_a_garbled_command_is_resent_even_when_not_idempotent(
    projector: SmartUX60, fake: FakeTransport
) -> None:
    """'invalid cmd=<something else>' means the device rejected (did not run) what it received."""
    fake.queue("invalid cmd=s\x00et volume+5", "volume=10")
    assert asyncio.run(projector.adjust_value("volume", 5)) == "10"
    assert fake.sent == ["set volume+5", "set volume+5"]


def test_persistently_garbled_command_gives_up(projector: SmartUX60, fake: FakeTransport) -> None:
    fake.queue(*["invalid cmd=garbage"] * 3)
    with pytest.raises(CommandRejectedError) as excinfo:
        asyncio.run(projector.get_value("x"))
    assert not isinstance(excinfo.value, DeviceIdleError)
    assert len(fake.sent) == 3


# ------------------------------------------------------------------ rejection handling


def test_rejection_while_idle_raises_device_idle_error(
    projector: SmartUX60, fake: FakeTransport
) -> None:
    fake.queue("invalid cmd=get frequency", "powerstate=Idle")
    with pytest.raises(DeviceIdleError, match="idle/off") as excinfo:
        asyncio.run(projector.get_value("frequency"))
    assert excinfo.value.command == "get frequency"
    assert str(excinfo.value).startswith("Command 'get frequency' is not available")
    assert fake.sent == ["get frequency", "get powerstate"]


def test_rejection_while_on_is_not_mislabelled_as_idle(
    projector: SmartUX60, fake: FakeTransport
) -> None:
    """E.g. a VGA-only setting queried while on HDMI: rejected, but the projector is on."""
    fake.queue("invalid cmd=get frequency", "powerstate=On")
    with pytest.raises(CommandRejectedError) as excinfo:
        asyncio.run(projector.get_value("frequency"))
    assert not isinstance(excinfo.value, DeviceIdleError)


def test_rejection_where_the_power_query_also_fails(
    projector: SmartUX60, fake: FakeTransport
) -> None:
    fake.queue("invalid cmd=get frequency", timeout("get powerstate"), timeout(), timeout())
    with pytest.raises(CommandRejectedError) as excinfo:
        asyncio.run(projector.get_value("frequency"))
    assert not isinstance(excinfo.value, DeviceIdleError)


def test_a_rejected_power_query_does_not_recurse(projector: SmartUX60, fake: FakeTransport) -> None:
    fake.queue("invalid cmd=get powerstate")
    with pytest.raises(CommandRejectedError):
        asyncio.run(projector.get_value("powerstate"))
    assert fake.sent == ["get powerstate"]


def test_rejection_matching_ignores_case_and_whitespace(
    projector: SmartUX60, fake: FakeTransport
) -> None:
    fake.queue("INVALID CMD= Get Frequency ", "powerstate=Idle")
    with pytest.raises(DeviceIdleError):
        asyncio.run(projector.get_value("frequency"))
