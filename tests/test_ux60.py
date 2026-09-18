from __future__ import annotations

import pytest

from smart_serial.devices.smart.ux60 import SmartUX60
from smart_serial.exceptions import CommandError
from smart_serial.utils.source import Source
from tests.conftest import FakeTransport


def _device(fake_transport: FakeTransport) -> SmartUX60:
    return SmartUX60(fake_transport)


# --- Generic get/set/adjust -------------------------------------------------


async def test_get_value_sends_get_command(fake_transport: FakeTransport) -> None:
    fake_transport.responses["get brightness"] = "brightness=55"
    device = _device(fake_transport)
    assert await device.get_value("brightness") == "55"
    assert fake_transport.sent == ["get brightness"]


async def test_set_value_sends_set_command(fake_transport: FakeTransport) -> None:
    fake_transport.responses["set brightness=65"] = "brightness=65"
    device = _device(fake_transport)
    assert await device.set_value("brightness", "65") == "65"


async def test_set_value_with_source_targets_inactive_source(
    fake_transport: FakeTransport,
) -> None:
    fake_transport.responses["set brightness vga1=65"] = "brightness vga1=65"
    device = _device(fake_transport)
    assert await device.set_value("brightness", "65", source="vga1") == "65"


async def test_adjust_value_uses_plus_for_positive_delta(fake_transport: FakeTransport) -> None:
    fake_transport.responses["set brightness+5"] = "brightness=70"
    device = _device(fake_transport)
    assert await device.adjust_value("brightness", 5) == "70"
    assert fake_transport.sent == ["set brightness+5"]


async def test_adjust_value_uses_minus_for_negative_delta(fake_transport: FakeTransport) -> None:
    fake_transport.responses["set brightness-15"] = "brightness=55"
    device = _device(fake_transport)
    assert await device.adjust_value("brightness", -15) == "55"
    assert fake_transport.sent == ["set brightness-15"]


async def test_invalid_command_raises_command_error(fake_transport: FakeTransport) -> None:
    # The real transport raises CommandError itself on an "invalid cmd="
    # reply; the fake transport just returns canned strings, so simulate
    # that behavior directly to prove the driver propagates it.
    class _RejectingTransport(type(fake_transport)):
        async def send_command(self, command: str) -> str:
            raise CommandError(command, "invalid cmd=[get frequency]")

    device = SmartUX60(_RejectingTransport())
    with pytest.raises(CommandError):
        await device.get_value("frequency")


# --- Power state -------------------------------------------------------------


async def test_power_on(fake_transport: FakeTransport) -> None:
    fake_transport.responses["on"] = "powerstate=Powering"
    device = _device(fake_transport)
    assert await device.power_on() == "Powering"
    assert fake_transport.sent == ["on"]


async def test_power_off_first_stage_returns_confirm_off(fake_transport: FakeTransport) -> None:
    fake_transport.responses["off"] = "powerstate=Confirm off"
    device = _device(fake_transport)
    assert await device.power_off() == "Confirm off"


async def test_power_off_now_sends_bare_verb(fake_transport: FakeTransport) -> None:
    fake_transport.responses["off now"] = "powerstate=Idle"
    device = _device(fake_transport)
    assert await device.power_off_now() == "Idle"
    assert fake_transport.sent == ["off now"]


async def test_get_power_state_uses_get_powerstate(fake_transport: FakeTransport) -> None:
    fake_transport.responses["get powerstate"] = "powerstate=On"
    device = _device(fake_transport)
    assert await device.get_power_state() == "On"
    assert fake_transport.sent == ["get powerstate"]


# --- Source selection ---------------------------------------------------------


async def test_select_input(fake_transport: FakeTransport) -> None:
    fake_transport.responses["set input=hdmi"] = "input=hdmi"
    device = _device(fake_transport)
    assert await device.select_input(Source("hdmi")) == Source("hdmi")


async def test_get_input_source_names(fake_transport: FakeTransport) -> None:
    fake_transport.responses["get input"] = "input=s-video"
    device = _device(fake_transport)
    input_source = await device.get_input()
    assert input_source == Source("s-video")
    assert input_source.display_name == "S-Video"
    assert str(input_source) == "s-video"
    assert fake_transport.sent == ["get input"]


async def test_get_video_inputs(
    fake_transport: FakeTransport,
) -> None:
    fake_transport.responses["get videoinputs"] = "videoinputs=vga1,vga2,s-video,composite,hdmi"
    device = _device(fake_transport)
    assert await device.get_video_inputs() == [
        Source("vga1"),
        Source("vga2"),
        Source("s-video"),
        Source("composite"),
        Source("hdmi"),
    ]
    assert fake_transport.sent == ["get videoinputs"]


async def test_select_input_accepts_gui_style_names(fake_transport: FakeTransport) -> None:
    fake_transport.responses["set input=hdmi"] = "input=hdmi"
    device = _device(fake_transport)
    assert Source("HDMI") == Source("hdmi")
    assert await device.select_input(Source("HDMI")) == Source("hdmi")


# --- Audio ---------------------------------------------------------------------


async def test_mute_and_unmute(fake_transport: FakeTransport) -> None:
    fake_transport.responses["set mute=on"] = "mute=on"
    fake_transport.responses["set mute=off"] = "mute=off"
    device = _device(fake_transport)
    assert await device.mute_audio() is True
    assert await device.unmute_audio() is False


async def test_set_volume(fake_transport: FakeTransport) -> None:
    fake_transport.responses["set volume=-5"] = "volume=-5"
    device = _device(fake_transport)
    assert await device.set_volume(-5) == -5


# --- Network ---------------------------------------------------------------------


async def test_network_enable_disable(fake_transport: FakeTransport) -> None:
    fake_transport.responses["set vgaoutnetenable=on"] = "vgaoutnetenable=on"
    fake_transport.responses["set vgaoutnetenable=off"] = "vgaoutnetenable=off"
    device = _device(fake_transport)
    assert await device.enable_network() is True
    assert await device.disable_network() is False


async def test_get_network_status(fake_transport: FakeTransport) -> None:
    fake_transport.responses["get netstatus"] = "netstatus=connected"
    device = _device(fake_transport)
    assert await device.get_network_status() == "connected"


# --- System ------------------------------------------------------------------------


async def test_get_lamp_hours(fake_transport: FakeTransport) -> None:
    fake_transport.responses["get lamphrs"] = "lamphrs=1234"
    device = _device(fake_transport)
    assert await device.get_lamp_hours() == 1234


async def test_reset_lamp_hours_sends_bare_set_with_no_value_echoed_back(
    fake_transport: FakeTransport,
) -> None:
    fake_transport.responses["set lamphrs=0"] = "lamphrs=0"
    device = _device(fake_transport)
    await device.reset_lamp_hours()
    assert fake_transport.sent == ["set lamphrs=0"]


async def test_restore_defaults_sends_bare_command(fake_transport: FakeTransport) -> None:
    fake_transport.responses["set restoredefaults"] = "restoredefaults=done"
    device = _device(fake_transport)
    await device.restore_defaults()
    assert fake_transport.sent == ["set restoredefaults"]
