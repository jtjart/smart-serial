"""Driver for the SMART UX60 ultra-short-throw projector.

Implements the RS-232 command set documented in Appendix B, "Remotely
managing your system through an RS-232 serial interface," of SMART's
"SMART Board 600ix interactive whiteboard system configuration and
user's guide." All command keys and behavior below are taken directly
from that reference.

Protocol summary (see Appendix B for full detail)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- Serial settings: 19200 baud, 8 data bits, no parity, 1 stop bit, no
  flow control. The projector's RS-232 port is a DCE device; a
  straight-through cable is used (pin 2 = transmit, pin 3 = receive,
  pin 5 = signal ground).
- Most settings follow a uniform ``get <key>`` / ``set <key>=<value>``
  convention, with adjustment commands ``set <key>+<n>`` / ``set
  <key>-<n>`` as an alternative to an absolute ``=<value>``. This driver
  exposes that convention directly via :meth:`get_value`,
  :meth:`set_value`, and :meth:`adjust_value`, so *every* documented
  command is usable even where no dedicated wrapper method exists below.
- Power commands are the one exception: ``on``, ``off``, ``off now``,
  and ``off low power`` are sent as bare verbs, not ``set``/``=`` pairs
  (querying is still ``get powerstate``, following the normal pattern).
- Video-source-scoped variants exist for some ``set`` commands (e.g.
  ``set brightness vga1=65``) to target a currently inactive source;
  pass ``source=`` on :meth:`set_value` / :meth:`adjust_value` for these.
"""

from __future__ import annotations

import ipaddress
from enum import StrEnum

from ...device import Device
from ...utils.source import Source


class PowerState(StrEnum):
    POWERING = "Powering"
    ON = "On"
    COOLING = "Cooling"
    CONFIRM_OFF = "Confirm off"
    IDLE = "Idle"


class DisplayMode(StrEnum):
    SMARTPRESENTATION = "SMARTpresentation"
    BRIGHTROOM = "brightroom"
    DARKROOM = "darkroom"
    SRGB = "sRGB"
    USER = "User"


class ClosedCaptioning(StrEnum):
    CC1 = "cc1"
    CC2 = "cc2"
    OFF = "off"


class NetworkStatus(StrEnum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    DISABLED = "disabled"


class AspectRatio(StrEnum):
    FILL = "fill"
    MATCH = "match"
    R16_9 = "16:9"


class ProjectionMode(StrEnum):
    FRONT = "front"
    CEILING = "ceiling"
    REAR = "rear"
    REAR_CEILING = "rear ceiling"


class StartupScreen(StrEnum):
    SMART = "smart"
    USERCAPTURE = "usercapture"
    PREVIEW = "preview"


class Language(StrEnum):
    CHINESE_SIMPLIFIED = "Chinese (Simplified)"
    CHINESE_TRADITIONAL = "Chinese (Traditional)"
    CZECH = "Czech"
    DANISH = "Danish"
    DUTCH = "Dutch"
    ENGLISH = "English"
    FINNISH = "Finnish"
    FRENCH = "French"
    GERMAN = "German"
    GREEK = "Greek"
    ITALIAN = "Italian"
    JAPANESE = "Japanese"
    KOREAN = "Korean"
    NORWEGIAN = "Norwegian"
    POLISH = "Polish"
    PORTUGUESE_BRAZIL = "Portuguese (Brazil)"
    PORTUGUESE_PORTUGAL = "Portuguese (Portugal)"
    RUSSIAN = "Russian"
    SPANISH = "Spanish"
    SWEDISH = "Swedish"


def _onoff(value: bool) -> str:
    return "on" if value else "off"


def _bool(value: str) -> bool:
    return value.strip().lower() == "on"


class SmartUX60(Device):
    """SMART UX60 ultra-short-throw projector (RS-232 control)."""

    vendor = "SMART Technologies"
    model = "UX60"

    # Confirmed: Appendix B, "Serial interface settings".
    default_baudrate = 19200

    # MARK: Value-based command methods

    async def get_value(self, key: str) -> str:
        """Send ``get <key>`` and return the raw value from the reply."""
        response = await self.transport.send_command(f"get {key}")
        return self._extract_value(response)

    async def set_value(self, key: str, value: str, *, source: Source | None = None) -> str:
        """Send ``set <key>[ <source>]=<value>`` and return the confirmed value.

        ``source`` targets a currently-inactive video source (e.g.
        ``"vga1"``) rather than the active one -- see "Video source
        specification values" in Appendix B. Only some ``set`` commands
        support this; check the command's table there.
        """
        target = f"{key} {source}" if source else key
        response = await self.transport.send_command(f"set {target}={value}")
        return self._extract_value(response)

    async def set_int_value(
        self, key: str, value: int, range: range, *, source: Source | None = None
    ) -> int:
        """Send ``set <key>[ <source>]=<value>`` and return the confirmed value.

        Raises :class:`ValueError` if the value is out of the given range.
        """
        if value not in range:
            raise ValueError(
                f"{key} {value} is out of range. Valid range: {range.start} to {range.stop - 1}"
            )
        return int(await self.set_value(key, str(value), source=source))

    async def adjust_value(self, key: str, delta: int, *, source: Source | None = None) -> str:
        """Send a relative adjustment, e.g. ``set brightness+5`` / ``set brightness-15``."""
        sign = "+" if delta >= 0 else "-"
        target = f"{key} {source}" if source else key
        response = await self.transport.send_command(f"set {target}{sign}{abs(delta)}")
        return self._extract_value(response)

    @staticmethod
    def _extract_value(response: str) -> str:
        _, separator, value = response.partition("=")
        return value if separator else response

    ###########################################
    # MARK: Power state
    # bare verbs -- the one non-get/set family
    ###########################################

    async def power_on(self) -> PowerState:
        return PowerState(self._extract_value(await self.transport.send_command("on")))

    async def power_off(self) -> PowerState:
        """Start the shutdown sequence.

        The projector requires a *second* ``power_off()`` within 10 seconds to actually enter
        Standby mode; the first call typically returns the ``"Confirm off"`` state.
        Use :meth:`power_off_now` to skip the confirmation step entirely.
        """
        return PowerState(self._extract_value(await self.transport.send_command("off")))

    async def power_off_now(self) -> PowerState:
        """Shut down immediately, bypassing the confirmation step. Cannot be cancelled."""
        return PowerState(self._extract_value(await self.transport.send_command("off now")))

    async def power_off_low_power(self) -> PowerState:
        return PowerState(self._extract_value(await self.transport.send_command("off low power")))

    async def get_power_state(self) -> PowerState:
        """Return the raw power state: Powering, On, Cooling, Confirm off, or Idle."""
        return PowerState(await self.get_value("powerstate"))

    #########################
    # MARK: Source selection
    #########################

    async def get_input(self) -> Source:
        return Source(await self.get_value("input"))

    async def get_video_inputs(self) -> list[Source]:
        """Return the available inputs in the user-friendly GUI format."""
        video_input_list = await self.get_value("videoinputs")
        if not video_input_list:
            return []
        return [Source(source) for source in video_input_list.split(",") if source]

    async def select_input(self, source: Source) -> Source:
        """Switch the active input."""
        return Source(await self.set_value("input", source.value))

    ################################
    # MARK: General source controls
    ################################

    async def get_display_mode(self) -> DisplayMode:
        return DisplayMode(await self.get_value("displaymode"))

    async def set_display_mode(self, mode: DisplayMode) -> DisplayMode:
        return DisplayMode(await self.set_value("displaymode", mode))

    brightness_range: range = range(101)

    async def get_brightness(self) -> int:
        return int(await self.get_value("brightness"))

    async def set_brightness(self, value: int, *, source: Source | None = None) -> int:
        """Brightness, 0-100."""
        return int(
            await self.set_int_value("brightness", value, self.brightness_range, source=source)
        )

    async def adjust_brightness(self, delta: int, *, source: Source | None = None) -> int:
        return int(await self.adjust_value("brightness", delta, source=source))

    contrast_range: range = range(101)

    async def get_contrast(self) -> int:
        return int(await self.get_value("contrast"))

    async def set_contrast(self, value: int, *, source: Source | None = None) -> int:
        """Contrast, 0-100."""
        return int(await self.set_int_value("contrast", value, self.contrast_range, source=source))

    async def adjust_contrast(self, delta: int, *, source: Source | None = None) -> int:
        return int(await self.adjust_value("contrast", delta, source=source))

    whitepeaking_range: range = range(11)

    async def get_whitepeaking(self) -> int:
        return int(await self.get_value("whitepeaking"))

    async def set_whitepeaking(self, value: int, *, source: Source | None = None) -> int:
        """White peaking, 0-10."""
        return int(
            await self.set_int_value("whitepeaking", value, self.whitepeaking_range, source=source)
        )

    async def adjust_whitepeaking(self, delta: int, *, source: Source | None = None) -> int:
        return int(await self.adjust_value("whitepeaking", delta, source=source))

    degamma_range: range = range(4)

    async def get_degamma(self) -> int:
        return int(await self.get_value("degamma"))

    async def set_degamma(self, value: int, *, source: Source | None = None) -> int:
        """Degamma, 0-3."""
        return int(await self.set_int_value("degamma", value, self.degamma_range, source=source))

    async def adjust_degamma(self, delta: int, *, source: Source | None = None) -> int:
        return int(await self.adjust_value("degamma", delta, source=source))

    color_range: range = range(101)

    async def get_red(self) -> int:
        return int(await self.get_value("red"))

    async def set_red(self, value: int, *, source: Source | None = None) -> int:
        """Red color setting, 0-100."""
        return int(await self.set_int_value("red", value, self.color_range, source=source))

    async def adjust_red(self, delta: int, *, source: Source | None = None) -> int:
        return int(await self.adjust_value("red", delta, source=source))

    async def get_green(self) -> int:
        return int(await self.get_value("green"))

    async def set_green(self, value: int, *, source: Source | None = None) -> int:
        """Green color setting, 0-100."""
        return int(await self.set_int_value("green", value, self.color_range, source=source))

    async def adjust_green(self, delta: int, *, source: Source | None = None) -> int:
        return int(await self.adjust_value("green", delta, source=source))

    async def get_blue(self) -> int:
        return int(await self.get_value("blue"))

    async def set_blue(self, value: int, *, source: Source | None = None) -> int:
        """Blue color setting, 0-100."""
        return int(await self.set_int_value("blue", value, self.color_range, source=source))

    async def adjust_blue(self, delta: int, *, source: Source | None = None) -> int:
        return int(await self.adjust_value("blue", delta, source=source))

    async def get_cyan(self) -> int:
        return int(await self.get_value("cyan"))

    async def set_cyan(self, value: int, *, source: Source | None = None) -> int:
        """Cyan color setting, 0-100."""
        return int(await self.set_int_value("cyan", value, self.color_range, source=source))

    async def adjust_cyan(self, delta: int, *, source: Source | None = None) -> int:
        return int(await self.adjust_value("cyan", delta, source=source))

    async def get_magenta(self) -> int:
        return int(await self.get_value("magenta"))

    async def set_magenta(self, value: int, *, source: Source | None = None) -> int:
        """Magenta color setting, 0-100."""
        return int(await self.set_int_value("magenta", value, self.color_range, source=source))

    async def adjust_magenta(self, delta: int, *, source: Source | None = None) -> int:
        return int(await self.adjust_value("magenta", delta, source=source))

    async def get_yellow(self) -> int:
        return int(await self.get_value("yellow"))

    async def set_yellow(self, value: int, *, source: Source | None = None) -> int:
        """Yellow color setting, 0-100."""
        return int(await self.set_int_value("yellow", value, self.color_range, source=source))

    async def adjust_yellow(self, delta: int, *, source: Source | None = None) -> int:
        return int(await self.adjust_value("yellow", delta, source=source))

    async def get_video_freeze(self) -> bool:
        return _bool(await self.get_value("videofreeze"))

    async def set_video_freeze(self, enabled: bool) -> bool:
        return _bool(await self.set_value("videofreeze", _onoff(enabled)))

    async def get_closed_captioning(self) -> ClosedCaptioning:
        return ClosedCaptioning(await self.get_value("cc"))

    async def set_closed_captioning(self, target: ClosedCaptioning) -> ClosedCaptioning:
        return ClosedCaptioning(await self.set_value("cc", target))

    ###################################
    # MARK: Additional source controls
    ###################################

    frequency_range: range = range(-5, 6)

    async def get_frequency(self) -> int:
        """Only for VGA sources"""
        return int(await self.get_value("frequency"))

    async def set_frequency(self, value: int, *, source: Source | None = None) -> int:
        """Only for VGA sources. Frequency offset setting, -5 to 5."""
        return int(
            await self.set_int_value("frequency", value, self.frequency_range, source=source)
        )

    tracking_range: range = range(32)

    async def get_tracking(self) -> int:
        """Only for VGA sources"""
        return int(await self.get_value("tracking"))

    async def set_tracking(self, value: int, *, source: Source | None = None) -> int:
        """Only for VGA sources. Tracking offset setting, 0 to 31."""
        return int(await self.set_int_value("tracking", value, self.tracking_range, source=source))

    saturation_range: range = range(101)

    async def get_saturation(self) -> int:
        """Only for VGA or composite video sources."""
        return int(await self.get_value("saturation"))

    async def set_saturation(self, value: int, *, source: Source | None = None) -> int:
        """Only for VGA or composite video sources. Saturation, 0 to 100."""
        return int(
            await self.set_int_value("saturation", value, self.saturation_range, source=source)
        )

    tint_range: range = range(101)

    async def get_tint(self) -> int:
        """Only for VGA or composite video sources."""
        return int(await self.get_value("tint"))

    async def set_tint(self, value: int, *, source: Source | None = None) -> int:
        """Only for VGA or composite video sources. Tint, 0 to 100."""
        return int(await self.set_int_value("tint", value, self.tint_range, source=source))

    sharpness_range: range = range(32)

    async def get_sharpness(self) -> int:
        """Only for VGA or composite video sources."""
        return int(await self.get_value("sharpness"))

    async def set_sharpness(self, value: int, *, source: Source | None = None) -> int:
        """Only for VGA or composite video sources. Sharpness, 0 to 31."""
        return int(
            await self.set_int_value("sharpness", value, self.sharpness_range, source=source)
        )

    #######################
    # MARK: Audio controls
    #######################

    volume_range: range = range(-20, 21)

    async def get_volume(self) -> int:
        return int(await self.get_value("volume"))

    async def set_volume(self, value: int) -> int:
        """Absolute volume, -20 to 20."""
        return int(await self.set_int_value("volume", value, self.volume_range))

    async def adjust_volume(self, delta: int) -> int:
        return int(await self.adjust_value("volume", delta))

    async def get_mute(self) -> bool:
        return _bool(await self.get_value("mute"))

    async def set_mute(self, value: bool) -> bool:
        return _bool(await self.set_value("mute", _onoff(value)))

    async def get_volume_control(self) -> bool:
        """``True`` if the projector's volume knob is enabled, ``False`` if disabled."""
        return _bool(await self.get_value("volumecontrol"))

    async def set_volume_control(self, enabled: bool) -> bool:
        """Enable or disable the projector's volume knob."""
        return _bool(await self.set_value("volumecontrol", _onoff(enabled)))

    #########################
    # MARK: Network controls
    #########################

    async def get_network_status(self) -> NetworkStatus:
        return NetworkStatus(await self.get_value("netstatus"))

    async def get_dhcp(self) -> bool:
        return _bool(await self.get_value("dhcp"))

    async def set_dhcp(self, enabled: bool) -> bool:
        return _bool(await self.set_value("dhcp", _onoff(enabled)))

    async def get_ip_address(self) -> ipaddress.IPv4Address:
        return ipaddress.IPv4Address(await self.get_value("ipaddr"))

    async def set_ip_address(self, value: ipaddress.IPv4Address) -> ipaddress.IPv4Address:
        return ipaddress.IPv4Address(await self.set_value("ipaddr", str(value)))

    async def get_subnet_mask(self) -> ipaddress.IPv4Address:
        return ipaddress.IPv4Address(await self.get_value("subnetmask"))

    async def set_subnet_mask(self, value: ipaddress.IPv4Address) -> ipaddress.IPv4Address:
        return ipaddress.IPv4Address(await self.set_value("subnetmask", str(value)))

    async def get_gateway(self) -> ipaddress.IPv4Address:
        return ipaddress.IPv4Address(await self.get_value("gateway"))

    async def set_gateway(self, value: ipaddress.IPv4Address) -> ipaddress.IPv4Address:
        return ipaddress.IPv4Address(await self.set_value("gateway", str(value)))

    async def get_primary_dns(self) -> ipaddress.IPv4Address:
        return ipaddress.IPv4Address(await self.get_value("primarydns"))

    async def set_primary_dns(self, value: ipaddress.IPv4Address) -> ipaddress.IPv4Address:
        return ipaddress.IPv4Address(await self.set_value("primarydns", str(value)))

    async def get_mac_address(self) -> str:
        return await self.get_value("macaddr")

    ###############
    # MARK: System
    ###############

    async def get_auto_signal(self) -> bool:
        return _bool(await self.get_value("autosignal"))

    async def set_auto_signal(self, enabled: bool) -> bool:
        return _bool(await self.set_value("autosignal", _onoff(enabled)))

    async def get_lamp_reminder(self) -> bool:
        return _bool(await self.get_value("lampreminder"))

    async def set_lamp_reminder(self, enabled: bool) -> bool:
        return _bool(await self.set_value("lampreminder", _onoff(enabled)))

    async def get_high_brightness(self) -> bool:
        return _bool(await self.get_value("highbrightness"))

    async def set_high_brightness(self, enabled: bool) -> bool:
        return _bool(await self.set_value("highbrightness", _onoff(enabled)))

    auto_power_off_range: range = range(241)

    async def get_auto_power_off(self) -> int:
        return int(await self.get_value("autopoweroff"))

    async def set_auto_power_off(self, value: int) -> int:
        return int(await self.set_int_value("autopoweroff", value, self.auto_power_off_range))

    zoom_range: range = range(31)

    async def get_zoom(self) -> int:
        return int(await self.get_value("zoom"))

    async def set_zoom(self, value: int) -> int:
        return int(await self.set_int_value("zoom", value, self.zoom_range))

    projector_id_range: range = range(100)

    async def get_projector_id(self) -> int:
        return int(await self.get_value("projectorid"))

    async def set_projector_id(self, value: int) -> int:
        return int(await self.set_int_value("projectorid", value, self.projector_id_range))

    hposition_range: range = range(101)

    async def get_hposition(self) -> int:
        return int(await self.get_value("hposition"))

    async def set_hposition(self, value: int) -> int:
        return int(await self.set_int_value("hposition", value, self.hposition_range))

    vposition_range: range = range(-5, 6)

    async def get_vposition(self) -> int:
        return int(await self.get_value("vposition"))

    async def set_vposition(self, value: int) -> int:
        return int(await self.set_int_value("vposition", value, self.vposition_range))

    async def get_aspect_ratio(self) -> AspectRatio:
        return AspectRatio(await self.get_value("aspectratio"))

    async def set_aspect_ratio(self, value: AspectRatio) -> AspectRatio:
        return AspectRatio(await self.set_value("aspectratio", value))

    async def get_projection_mode(self) -> ProjectionMode:
        return ProjectionMode(await self.get_value("projectionmode"))

    async def set_projection_mode(self, value: ProjectionMode) -> ProjectionMode:
        return ProjectionMode(await self.set_value("projectionmode", value))

    async def get_startup_screen(self) -> StartupScreen:
        return StartupScreen(await self.get_value("startupscreen"))

    async def set_startup_screen(self, value: StartupScreen) -> StartupScreen:
        return StartupScreen(await self.set_value("startupscreen", value))

    async def get_resolution(self) -> str:
        return await self.get_value("resolution")

    async def get_language(self) -> Language:
        return Language(await self.get_value("language"))

    async def set_language(self, value: Language) -> Language:
        return Language(await self.set_value("language", value))

    async def get_group_name(self) -> str:
        return await self.get_value("groupname")

    async def set_group_name(self, value: str) -> str:
        """Enter a descriptor no more than 12 characters long."""
        if len(value) > 12:
            raise ValueError("Descriptor is longer than 12 characters.")
        return str(await self.set_value("groupname", value))

    async def get_projector_name(self) -> str:
        return await self.get_value("projectorname")

    async def set_projector_name(self, value: str) -> str:
        """Enter a descriptor no more than 12 characters long."""
        if len(value) > 12:
            raise ValueError("Descriptor is longer than 12 characters.")
        return str(await self.set_value("projectorname", value))

    async def get_location_info(self) -> str:
        return await self.get_value("locationinfo")

    async def set_location_info(self, value: str) -> str:
        """Enter a descriptor no more than 16 characters long."""
        if len(value) > 16:
            raise ValueError("Descriptor is longer than 16 characters.")
        return str(await self.set_value("locationinfo", value))

    async def get_contact_info(self) -> str:
        return await self.get_value("contactinfo")

    async def set_contact_info(self, value: str) -> str:
        """Enter a descriptor no more than 16 characters long."""
        if len(value) > 16:
            raise ValueError("Descriptor is longer than 16 characters.")
        return str(await self.set_value("contactinfo", value))

    async def get_model_number(self) -> str:
        return await self.get_value("modelnum")

    async def get_video_mute(self) -> bool:
        return _bool(await self.get_value("videomute"))

    async def set_video_mute(self, value: bool) -> bool:
        return _bool(await self.set_value("videomute", _onoff(value)))

    async def restore_defaults(self) -> bool:
        return (
            self._extract_value(await self.transport.send_command("set restoredefaults")) == "done"
        )

    async def get_serial_number(self) -> str:
        return await self.get_value("serialnum")

    async def get_lamp_hours(self) -> int:
        return int(await self.get_value("lamphrs"))

    async def reset_lamp_hours(self) -> int:
        return int(await self.set_value("lamphrs", "0"))

    async def get_system_hours(self) -> int:
        return int(await self.get_value("syshrs"))

    async def get_projector_firmware_version(self) -> str:
        return await self.get_value("fwverddp")

    async def get_network_firmware_version(self) -> str:
        return await self.get_value("fwvernet")

    async def get_processor_firmware_version(self) -> str:
        return await self.get_value("fwvermpu")

    async def get_esp_firmware_version(self) -> str:
        return await self.get_value("fwverecp")

    async def get_vga_out_and_network_enabled(self) -> bool:
        return _bool(await self.get_value("vgaoutnetenable"))

    async def set_vga_out_and_network_enabled(self, value: bool) -> bool:
        return _bool(await self.set_value("vgaoutnetenable", _onoff(value)))

    async def get_signal_detected(self) -> bool:
        return await self.get_value("signaldetected") == "true"

    async def get_usb1source(self) -> Source | None:
        source = await self.get_value("usb1source")
        if source == "disabled":
            return None
        return Source(source)

    async def set_usb1source(self, source: Source | None) -> Source | None:
        if source is None:
            await self.set_value("usb1source", "disabled")
            return None
        return Source(await self.set_value("usb1source", source.value))

    async def get_usb2source(self) -> Source | None:
        source = await self.get_value("usb2source")
        if source == "disabled":
            return None
        return Source(source)

    async def set_usb2source(self, source: Source | None) -> Source | None:
        if source is None:
            await self.set_value("usb2source", "disabled")
            return None
        return Source(await self.set_value("usb2source", source.value))
