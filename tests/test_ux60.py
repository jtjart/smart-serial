from __future__ import annotations

import asyncio
import ipaddress
from typing import TYPE_CHECKING, assert_type

import pytest

from smart_serial import SmartDevice, SmartUX60, Source, UnexpectedResponseError
from smart_serial.devices.settings import (
    AdjustableIntSetting,
    IntSetting,
    ReadOnlySetting,
    Setting,
)
from smart_serial.devices.ux60 import DisplayMode, Language, NetworkStatus, PowerState

if TYPE_CHECKING:
    from conftest import FakeTransport


# ------------------------------------------------------------------ typed settings


def test_int_get_set_adjust(projector: SmartUX60, fake: FakeTransport) -> None:
    fake.queue("brightness=45", "brightness=65", "brightness=55", "brightness=60")

    async def scenario() -> None:
        got = await projector.brightness.get()
        assert_type(got, int)
        assert got == 45
        assert await projector.brightness.set(65) == 65
        assert await projector.brightness.adjust(-10) == 55
        assert await projector.brightness.adjust(5) == 60

    asyncio.run(scenario())
    assert fake.sent == [
        "get brightness",
        "set brightness=65",
        "set brightness-10",
        "set brightness+5",
    ]


def test_int_out_of_range_raises_and_sends_nothing(
    projector: SmartUX60, fake: FakeTransport
) -> None:
    with pytest.raises(ValueError, match=r"'brightness'.*out of range.*0 to 100"):
        asyncio.run(projector.brightness.set(101))
    with pytest.raises(ValueError, match="out of range"):
        asyncio.run(projector.volume.set(-21))
    assert fake.sent == []


def test_per_source_targets_an_inactive_input(projector: SmartUX60, fake: FakeTransport) -> None:
    fake.queue("brightness=65", "brightness=70")
    asyncio.run(projector.brightness.set(65, source="vga1"))
    asyncio.run(projector.brightness.adjust(5, source=Source("VGA 1")))
    assert fake.sent == ["set brightness vga1=65", "set brightness vga1+5"]


def test_source_rejected_for_settings_that_are_not_per_source(
    projector: SmartUX60, fake: FakeTransport
) -> None:
    with pytest.raises(ValueError, match="cannot target a specific source"):
        asyncio.run(projector.volume.set(5, source="vga1"))
    assert fake.sent == []


def test_bool_setting(projector: SmartUX60, fake: FakeTransport) -> None:
    fake.queue("mute=on", "mute=off")

    async def scenario() -> None:
        assert await projector.mute.get() is True
        assert await projector.mute.set(False) is False

    asyncio.run(scenario())
    assert fake.sent == ["get mute", "set mute=off"]


def test_bool_garbage_is_a_library_error_not_silently_false(
    projector: SmartUX60, fake: FakeTransport
) -> None:
    fake.queue("mute=maybe")
    with pytest.raises(UnexpectedResponseError, match="maybe"):
        asyncio.run(projector.mute.get())


def test_enum_setting_is_case_insensitive_on_read(
    projector: SmartUX60, fake: FakeTransport
) -> None:
    fake.queue("displaymode=DARKROOM", "displaymode=sRGB")

    async def scenario() -> None:
        mode = await projector.display_mode.get()
        assert_type(mode, DisplayMode)
        assert mode is DisplayMode.DARKROOM
        assert await projector.display_mode.set(DisplayMode.SRGB) is DisplayMode.SRGB

    asyncio.run(scenario())
    assert fake.sent == ["get displaymode", "set displaymode=sRGB"]  # exact casing on write


def test_enum_unknown_value_is_a_library_error(projector: SmartUX60, fake: FakeTransport) -> None:
    fake.queue("displaymode=disco")
    with pytest.raises(UnexpectedResponseError):
        asyncio.run(projector.display_mode.get())


def test_language_with_spaces_and_parentheses(projector: SmartUX60, fake: FakeTransport) -> None:
    fake.queue("language=Portuguese (Brazil)")
    assert asyncio.run(projector.language.get()) is Language.PORTUGUESE_BRAZIL


def test_ip_settings(projector: SmartUX60, fake: FakeTransport) -> None:
    fake.queue("ipaddr=192.168.1.5", "gateway=192.168.1.1")

    async def scenario() -> None:
        ip = await projector.ip_address.get()
        assert_type(ip, ipaddress.IPv4Address)
        assert ip == ipaddress.IPv4Address("192.168.1.5")
        await projector.gateway.set(ipaddress.IPv4Address("192.168.1.1"))

    asyncio.run(scenario())
    assert fake.sent == ["get ipaddr", "set gateway=192.168.1.1"]


def test_string_length_limit(projector: SmartUX60, fake: FakeTransport) -> None:
    with pytest.raises(ValueError, match="longer than 12"):
        asyncio.run(projector.group_name.set("x" * 13))
    fake.queue("groupname=Room 101")
    assert asyncio.run(projector.group_name.set("Room 101")) == "Room 101"


def test_string_values_cannot_smuggle_a_second_command(
    projector: SmartUX60, fake: FakeTransport
) -> None:
    with pytest.raises(ValueError, match="line breaks"):
        asyncio.run(projector.location_info.set("a\rset volume=20"))
    assert fake.sent == []


def test_optional_source_setting(projector: SmartUX60, fake: FakeTransport) -> None:
    fake.queue("usb1source=disabled", "usb1source=hdmi1", "usb1source=disabled")

    async def scenario() -> None:
        assert await projector.usb1_source.get() is None
        assert await projector.usb1_source.get() == Source("hdmi1")
        assert await projector.usb1_source.set(None) is None

    asyncio.run(scenario())
    assert fake.sent == ["get usb1source", "get usb1source", "set usb1source=disabled"]


def test_read_only_settings_have_no_setter(projector: SmartUX60, fake: FakeTransport) -> None:
    fake.queue("serialnum=ABC123")
    assert asyncio.run(projector.serial_number.get()) == "ABC123"
    assert not hasattr(projector.serial_number, "set")


def test_assigning_to_a_setting_fails_loudly(projector: SmartUX60) -> None:
    with pytest.raises(AttributeError, match="is a setting"):
        projector.brightness = 5  # would otherwise silently shadow the descriptor


def test_signal_detected_and_lamp_hours(projector: SmartUX60, fake: FakeTransport) -> None:
    fake.queue("signaldetected=true", "lamphrs=1234", "lamphrs=0")

    async def scenario() -> None:
        assert await projector.signal_detected.get() is True
        assert await projector.lamp_hours.get() == 1234
        assert await projector.reset_lamp_hours() == 0

    asyncio.run(scenario())
    assert fake.sent == ["get signaldetected", "get lamphrs", "set lamphrs=0"]


def test_network_status(projector: SmartUX60, fake: FakeTransport) -> None:
    fake.queue("netstatus=disabled")
    assert asyncio.run(projector.network_status.get()) is NetworkStatus.DISABLED


# --------------------------------------------------------------------- introspection


def test_class_level_access_returns_the_declaration_with_metadata() -> None:
    assert isinstance(SmartUX60.brightness, IntSetting)
    assert SmartUX60.brightness.bounds == range(101)
    assert SmartUX60.volume.bounds == range(-20, 21)
    assert SmartUX60.display_mode.enum is DisplayMode
    assert SmartUX60.group_name.max_length == 12
    assert "VGA" in SmartUX60.frequency.doc


def test_settings_registry_is_complete_and_consistent() -> None:
    registry = SmartUX60.settings()
    assert len(registry) > 60
    for attr_name, setting in registry.items():
        assert setting.name == attr_name  # __set_name__ ran
        assert setting.key and setting.key == setting.key.strip()
        assert " " not in setting.key
    keys = [setting.key for setting in registry.values()]
    assert len(keys) == len(set(keys)), "two attributes declare the same device key"
    assert isinstance(registry["serial_number"], ReadOnlySetting)
    assert not isinstance(registry["serial_number"], Setting)
    assert isinstance(registry["brightness"], IntSetting)


def test_a_generic_integration_can_enumerate_number_entities() -> None:
    """The point of declarative settings: metadata without per-setting code."""
    numbers = {
        name: (setting.bounds.start, setting.bounds.stop - 1)
        for name, setting in SmartUX60.settings().items()
        if isinstance(setting, IntSetting)
    }
    assert numbers["brightness"] == (0, 100)
    assert numbers["volume"] == (-20, 20)
    assert numbers["vertical_position"] == (-5, 5)


def test_smart_device_base_has_no_settings() -> None:
    assert SmartDevice.settings() == {}


# --------------------------------------------------------------------------- inputs


def test_select_input_accepts_a_string(projector: SmartUX60, fake: FakeTransport) -> None:
    fake.queue("input=hdmi1")
    result = asyncio.run(projector.select_input("HDMI 1"))
    assert_type(result, Source)
    assert result == Source("hdmi1")
    assert fake.sent == ["set input=hdmi1"]


def test_get_input_and_video_inputs(projector: SmartUX60, fake: FakeTransport) -> None:
    fake.queue("input=vga1", "videoinputs=vga1,hdmi1,hdmi2", "videoinputs=")

    async def scenario() -> None:
        assert await projector.get_input() == Source("vga1")
        assert await projector.get_video_inputs() == [
            Source("vga1"),
            Source("hdmi1"),
            Source("hdmi2"),
        ]
        assert await projector.get_video_inputs() == []

    asyncio.run(scenario())


# ---------------------------------------------------------------------------- power


def test_raw_power_commands(projector: SmartUX60, fake: FakeTransport) -> None:
    fake.queue("powerstate=Powering", "powerstate=Confirm off", "powerstate=Cooling")

    async def scenario() -> None:
        assert await projector.power_on() is PowerState.POWERING
        assert await projector.power_off() is PowerState.CONFIRM_OFF
        assert await projector.power_off_now() is PowerState.COOLING

    asyncio.run(scenario())
    assert fake.sent == ["on", "off", "off now"]


def test_turn_off(projector: SmartUX60, fake: FakeTransport) -> None:
    fake.queue("powerstate=Cooling")
    asyncio.run(projector.turn_off())
    assert fake.sent == ["off now"]


def test_turn_on_and_is_on(projector: SmartUX60, fake: FakeTransport) -> None:
    fake.queue(
        "powerstate=Powering",
        "powerstate=On",
        "powerstate=Powering",
        "powerstate=Cooling",
        "powerstate=Idle",
        "powerstate=Confirm off",
    )

    async def scenario() -> None:
        await projector.turn_on()
        assert [await projector.is_on() for _ in range(5)] == [True, True, False, False, True]

    asyncio.run(scenario())
    assert fake.sent == ["on"] + ["get powerstate"] * 5


def test_get_power_state_accepts_any_casing(projector: SmartUX60, fake: FakeTransport) -> None:
    fake.queue("powerstate=confirm OFF")
    assert asyncio.run(projector.get_power_state()) is PowerState.CONFIRM_OFF


# -------------------------------------------------------------- generic value access


def test_generic_accessors_from_the_readme(projector: SmartUX60, fake: FakeTransport) -> None:
    fake.queue("frequency=0", "saturation=80", "brightness=45", "brightness=65")

    async def scenario() -> None:
        assert await projector.get_value("frequency") == "0"
        assert await projector.set_value("saturation", "80") == "80"
        assert await projector.adjust_value("brightness", -10) == "45"
        # source may be a plain string, as the README shows
        assert await projector.set_value("brightness", "65", source="vga1") == "65"

    asyncio.run(scenario())
    assert fake.sent == [
        "get frequency",
        "set saturation=80",
        "set brightness-10",
        "set brightness vga1=65",
    ]


def test_restore_defaults(projector: SmartUX60, fake: FakeTransport) -> None:
    fake.queue("restoredefaults=done", "restoredefaults=failed")

    async def scenario() -> None:
        assert await projector.restore_defaults() is True
        assert await projector.restore_defaults() is False

    asyncio.run(scenario())
    assert fake.sent == ["set restoredefaults", "set restoredefaults"]


def test_only_the_documented_settings_are_adjustable() -> None:
    """Mirrors the previous adjust_* methods; e.g. ``zoom+1`` was never exposed."""
    adjustable = {
        name
        for name, setting in SmartUX60.settings().items()
        if isinstance(setting, AdjustableIntSetting)
    }
    assert adjustable == {
        "brightness", "contrast", "white_peaking", "degamma", "volume",
        "red", "green", "blue", "cyan", "magenta", "yellow",
    }  # fmt: skip
    assert not hasattr(SmartUX60.zoom, "adjust")


def test_per_source_settings_match_the_previous_api() -> None:
    per_source = {n for n, s in SmartUX60.settings().items() if getattr(s, "per_source", False)}
    assert per_source == {
        "brightness", "contrast", "white_peaking", "degamma", "red", "green", "blue", "cyan",
        "magenta", "yellow", "frequency", "tracking", "saturation", "tint", "sharpness",
    }  # fmt: skip
