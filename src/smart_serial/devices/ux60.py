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
  convention, with ``set <key>+<n>`` / ``set <key>-<n>`` as a relative
  alternative for some of them (declared as ``AdjustableIntSetting``). That
  convention is implemented once in
  :class:`~smart_serial.devices.base.SmartDevice`; this module just
  *declares* the settings (see :mod:`smart_serial.devices.settings`).
  Every documented command is also reachable through the generic
  :meth:`get_value` / :meth:`set_value` / :meth:`adjust_value`.
- Power commands are the one exception: ``on``, ``off``, ``off now``, and
  ``off low power`` are sent as bare verbs (querying is still
  ``get powerstate``).
- Video-source-scoped variants exist for some ``set`` commands (e.g.
  ``set brightness vga1=65``) to target a currently inactive source; those
  settings are declared ``per_source=True`` and accept ``source=``.
"""

from __future__ import annotations

from typing import ClassVar

from ..source import Source
from ..transport import SerialSettings
from .base import CaseInsensitiveStrEnum, SmartDevice
from .settings import (
    BOOL,
    INT,
    STR,
    AdjustableIntSetting,
    BoolSetting,
    EnumCodec,
    EnumSetting,
    IntSetting,
    IPv4Setting,
    OptionalCodec,
    ReadOnlySetting,
    Setting,
    SourceCodec,
    SourceListCodec,
    StrSetting,
    parse_reply,
)


class PowerState(CaseInsensitiveStrEnum):
    POWERING = "Powering"
    ON = "On"
    COOLING = "Cooling"
    CONFIRM_OFF = "Confirm off"
    IDLE = "Idle"


class DisplayMode(CaseInsensitiveStrEnum):
    SMARTPRESENTATION = "SMARTpresentation"
    BRIGHTROOM = "brightroom"
    DARKROOM = "darkroom"
    SRGB = "sRGB"
    USER = "User"


class ClosedCaptioning(CaseInsensitiveStrEnum):
    CC1 = "cc1"
    CC2 = "cc2"
    OFF = "off"


class NetworkStatus(CaseInsensitiveStrEnum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    DISABLED = "disabled"


class AspectRatio(CaseInsensitiveStrEnum):
    FILL = "fill"
    MATCH = "match"
    R16_9 = "16:9"


class ProjectionMode(CaseInsensitiveStrEnum):
    FRONT = "front"
    CEILING = "ceiling"
    REAR = "rear"
    REAR_CEILING = "rear ceiling"


class StartupScreen(CaseInsensitiveStrEnum):
    SMART = "smart"
    USERCAPTURE = "usercapture"
    PREVIEW = "preview"


class Language(CaseInsensitiveStrEnum):
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


_POWER_STATE = EnumCodec(PowerState)


class SmartUX60(SmartDevice):
    """SMART UX60 ultra-short-throw projector (RS-232 control).

    Settings are attributes: ``await projector.brightness.set(65)``. Use
    :meth:`~SmartDevice.settings` to enumerate them, and e.g.
    ``SmartUX60.brightness.bounds`` to read their metadata without a device.
    """

    vendor = "SMART Technologies"
    model = "UX60"

    # Confirmed: Appendix B, "Serial interface settings".
    serial_settings: ClassVar[SerialSettings] = SerialSettings(baudrate=19200)

    # ------------------------------------------------------------------ power
    # Bare verbs -- the one non-get/set family -- plus the ``powerstate`` query.

    power_state: ReadOnlySetting[PowerState] = ReadOnlySetting(
        "powerstate", _POWER_STATE, doc="Powering, On, Cooling, Confirm off or Idle."
    )

    async def power_on(self) -> PowerState:
        """Send ``on`` and return the resulting power state."""
        raw = await self.send_verb("on", retry_on_timeout=True)
        return parse_reply(_POWER_STATE, raw, "on")

    async def power_off(self) -> PowerState:
        """Start the shutdown sequence (the raw, first stage).

        The projector requires a *second* ``power_off()`` within 10 seconds to
        actually enter Standby; the first call typically returns
        :attr:`PowerState.CONFIRM_OFF`. Use :meth:`turn_off` to have that handled for you,
        or :meth:`power_off_now` to skip confirmation entirely.
        """
        raw = await self.send_verb("off")
        return parse_reply(_POWER_STATE, raw, "off")

    async def power_off_now(self) -> PowerState:
        """Shut down immediately, bypassing the confirmation step. Cannot be cancelled."""
        raw = await self.send_verb("off now")
        return parse_reply(_POWER_STATE, raw, "off now")

    async def power_off_low_power(self) -> PowerState:
        raw = await self.send_verb("off low power")
        return parse_reply(_POWER_STATE, raw, "off low power")

    async def get_power_state(self) -> PowerState:
        """Return the power state: Powering, On, Cooling, Confirm off, or Idle."""
        return await self.power_state.get()

    # The generic :class:`~smart_serial.capabilities.PowerControl` API.

    async def turn_on(self) -> PowerState:
        return await self.power_on()

    async def turn_off(self) -> PowerState:
        return await self.power_off_now()

    async def is_on(self) -> bool:
        """``True`` while the projector is on or warming up."""
        return await self.get_power_state() in (
            PowerState.ON,
            PowerState.POWERING,
            PowerState.CONFIRM_OFF,
        )

    # ---------------------------------------------------------------- sources

    input_source: Setting[Source] = Setting("input", SourceCodec(), doc="The active video input.")
    video_inputs: ReadOnlySetting[tuple[Source, ...]] = ReadOnlySetting(
        "videoinputs", SourceListCodec(), doc="The video inputs available on this unit."
    )

    async def get_input(self) -> Source:
        return await self.input_source.get()

    async def select_input(self, source: Source | str) -> Source:
        """Switch the active input. Accepts a :class:`Source` or its name (``"HDMI 1"``)."""
        return await self.input_source.set(Source.coerce(source))

    async def get_video_inputs(self) -> list[Source]:
        """Return the available inputs."""
        return list(await self.video_inputs.get())

    # ------------------------------------------------- general source controls

    display_mode: EnumSetting[DisplayMode] = EnumSetting("displaymode", DisplayMode)
    brightness: AdjustableIntSetting = AdjustableIntSetting(
        "brightness", range(101), per_source=True
    )
    contrast: AdjustableIntSetting = AdjustableIntSetting("contrast", range(101), per_source=True)
    white_peaking: AdjustableIntSetting = AdjustableIntSetting(
        "whitepeaking", range(11), per_source=True
    )
    degamma: AdjustableIntSetting = AdjustableIntSetting("degamma", range(4), per_source=True)
    red: AdjustableIntSetting = AdjustableIntSetting("red", range(101), per_source=True)
    green: AdjustableIntSetting = AdjustableIntSetting("green", range(101), per_source=True)
    blue: AdjustableIntSetting = AdjustableIntSetting("blue", range(101), per_source=True)
    cyan: AdjustableIntSetting = AdjustableIntSetting("cyan", range(101), per_source=True)
    magenta: AdjustableIntSetting = AdjustableIntSetting("magenta", range(101), per_source=True)
    yellow: AdjustableIntSetting = AdjustableIntSetting("yellow", range(101), per_source=True)
    video_freeze: BoolSetting = BoolSetting("videofreeze")
    closed_captioning: EnumSetting[ClosedCaptioning] = EnumSetting("cc", ClosedCaptioning)

    # ---------------------------------------------- additional source controls

    frequency: IntSetting = IntSetting(
        "frequency", range(-5, 6), per_source=True, doc="Frequency offset. VGA sources only."
    )
    tracking: IntSetting = IntSetting(
        "tracking", range(32), per_source=True, doc="Tracking offset. VGA sources only."
    )
    saturation: IntSetting = IntSetting(
        "saturation", range(101), per_source=True, doc="VGA or composite video sources only."
    )
    tint: IntSetting = IntSetting(
        "tint", range(101), per_source=True, doc="VGA or composite video only."
    )
    sharpness: IntSetting = IntSetting(
        "sharpness", range(32), per_source=True, doc="VGA or composite video sources only."
    )

    # ------------------------------------------------------------------ audio

    volume: AdjustableIntSetting = AdjustableIntSetting("volume", range(-20, 21))
    mute: BoolSetting = BoolSetting("mute")
    volume_control: BoolSetting = BoolSetting(
        "volumecontrol", doc="Whether the projector's own volume knob is enabled."
    )

    # ---------------------------------------------------------------- network

    network_status: ReadOnlySetting[NetworkStatus] = ReadOnlySetting(
        "netstatus", EnumCodec(NetworkStatus)
    )
    dhcp: BoolSetting = BoolSetting("dhcp")
    ip_address: IPv4Setting = IPv4Setting("ipaddr")
    subnet_mask: IPv4Setting = IPv4Setting("subnetmask")
    gateway: IPv4Setting = IPv4Setting("gateway")
    primary_dns: IPv4Setting = IPv4Setting("primarydns")
    mac_address: ReadOnlySetting[str] = ReadOnlySetting("macaddr", STR)

    # ----------------------------------------------------------------- system

    auto_signal: BoolSetting = BoolSetting("autosignal")
    lamp_reminder: BoolSetting = BoolSetting("lampreminder")
    high_brightness: BoolSetting = BoolSetting("highbrightness")
    auto_power_off: IntSetting = IntSetting("autopoweroff", range(241))
    zoom: IntSetting = IntSetting("zoom", range(31))
    projector_id: IntSetting = IntSetting("projectorid", range(100))
    horizontal_position: IntSetting = IntSetting("hposition", range(101))
    vertical_position: IntSetting = IntSetting("vposition", range(-5, 6))
    aspect_ratio: EnumSetting[AspectRatio] = EnumSetting("aspectratio", AspectRatio)
    projection_mode: EnumSetting[ProjectionMode] = EnumSetting("projectionmode", ProjectionMode)
    startup_screen: EnumSetting[StartupScreen] = EnumSetting("startupscreen", StartupScreen)
    resolution: ReadOnlySetting[str] = ReadOnlySetting("resolution", STR)
    language: EnumSetting[Language] = EnumSetting("language", Language)
    group_name: StrSetting = StrSetting("groupname", max_length=12)
    projector_name: StrSetting = StrSetting("projectorname", max_length=12)
    location_info: StrSetting = StrSetting("locationinfo", max_length=16)
    contact_info: StrSetting = StrSetting("contactinfo", max_length=16)
    model_number: ReadOnlySetting[str] = ReadOnlySetting("modelnum", STR)
    video_mute: BoolSetting = BoolSetting("videomute")
    serial_number: ReadOnlySetting[str] = ReadOnlySetting("serialnum", STR)
    lamp_hours: ReadOnlySetting[int] = ReadOnlySetting("lamphrs", INT)
    system_hours: ReadOnlySetting[int] = ReadOnlySetting("syshrs", INT)
    projector_firmware_version: ReadOnlySetting[str] = ReadOnlySetting("fwverddp", STR)
    network_firmware_version: ReadOnlySetting[str] = ReadOnlySetting("fwvernet", STR)
    processor_firmware_version: ReadOnlySetting[str] = ReadOnlySetting("fwvermpu", STR)
    esp_firmware_version: ReadOnlySetting[str] = ReadOnlySetting("fwverecp", STR)
    vga_out_and_network_enabled: BoolSetting = BoolSetting(
        "vgaoutnetenable", doc="Off by default; must be enabled for network control or VGA out."
    )
    signal_detected: ReadOnlySetting[bool] = ReadOnlySetting("signaldetected", BOOL)
    usb1_source: Setting[Source | None] = Setting(
        "usb1source", OptionalCodec(SourceCodec()), doc="Input routed to USB 1; None if disabled."
    )
    usb2_source: Setting[Source | None] = Setting(
        "usb2source", OptionalCodec(SourceCodec()), doc="Input routed to USB 2; None if disabled."
    )

    async def reset_lamp_hours(self) -> int:
        """Reset the lamp-hours counter to zero."""
        return parse_reply(INT, await self.set_value("lamphrs", "0"), "set lamphrs=0")

    async def restore_defaults(self) -> bool:
        """Restore factory defaults. Returns ``True`` if the projector reports ``done``."""
        reply = await self._send("set restoredefaults", retry_on_timeout=False)
        return self._extract_value(reply) == "done"
