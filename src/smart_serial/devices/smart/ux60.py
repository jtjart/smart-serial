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

from ...device import Device
from ...registry import register


def _onoff(value: bool) -> str:
    return "on" if value else "off"


def _bool(value: str) -> bool:
    return value.strip().lower() == "on"


@register
class SmartUX60(Device):
    """SMART UX60 ultra-short-throw projector (RS-232 control)."""

    vendor = "smart"
    model = "ux60"

    # Confirmed: Appendix B, "Serial interface settings".
    default_baudrate = 19200

    # --- Generic key=value access -------------------------------------
    # Covers every command in Appendix B, including ones without a
    # dedicated wrapper method below.

    async def get_value(self, key: str) -> str:
        """Send ``get <key>`` and return the raw value from the reply."""
        response = await self.transport.send_command(f"get {key}")
        return self._extract_value(response)

    async def set_value(self, key: str, value: str, *, source: str | None = None) -> str:
        """Send ``set <key>[ <source>]=<value>`` and return the confirmed value.

        ``source`` targets a currently-inactive video source (e.g.
        ``"vga1"``) rather than the active one -- see "Video source
        specification values" in Appendix B. Only some ``set`` commands
        support this; check the command's table there.
        """
        target = f"{key} {source}" if source else key
        response = await self.transport.send_command(f"set {target}={value}")
        return self._extract_value(response)

    async def adjust_value(self, key: str, delta: int, *, source: str | None = None) -> str:
        """Send a relative adjustment, e.g. ``set brightness+5`` / ``set brightness-15``."""
        sign = "+" if delta >= 0 else "-"
        target = f"{key} {source}" if source else key
        response = await self.transport.send_command(f"set {target}{sign}{abs(delta)}")
        return self._extract_value(response)

    @staticmethod
    def _extract_value(response: str) -> str:
        _, separator, value = response.partition("=")
        return value if separator else response

    # --- Power state controls (bare verbs -- the one non-get/set family) -----

    async def power_on(self) -> str:
        return self._extract_value(await self.transport.send_command("on"))

    async def power_off(self) -> str:
        """Start the shutdown sequence.

        The projector requires a *second* ``power_off()`` within 10
        seconds to actually enter Standby mode; the first call typically
        returns the ``"Confirm off"`` state. Use :meth:`power_off_now`
        to skip the confirmation step entirely.
        """
        return self._extract_value(await self.transport.send_command("off"))

    async def power_off_now(self) -> str:
        """Shut down immediately, bypassing the confirmation step. Cannot be cancelled."""
        return self._extract_value(await self.transport.send_command("off now"))

    async def power_off_low_power(self) -> str:
        return self._extract_value(await self.transport.send_command("off low power"))

    async def get_power_state(self) -> str:
        """Return the raw power state: Powering, On, Cooling, Confirm off, or Idle."""
        return await self.get_value("powerstate")

    # --- Source selection -----------------------------------------------

    async def get_input(self) -> str:
        return await self.get_value("input")

    async def select_input(self, source: str) -> str:
        """Switch the active input: ``"VGA1"``, ``"VGA2"``, ``"Composite"``, or ``"HDMI"``."""
        return await self.set_value("input", source)

    # --- General source (display) controls -------------------------------

    async def get_display_mode(self) -> str:
        return await self.get_value("displaymode")

    async def set_display_mode(self, mode: str) -> str:
        """One of ``"SMARTpresentation"``, ``"brightroom"``, ``"darkroom"``,
        ``"sRGB"``, or ``"User"``.
        """
        return await self.set_value("displaymode", mode)

    async def get_brightness(self) -> int:
        return int(await self.get_value("brightness"))

    async def set_brightness(self, value: int, *, source: str | None = None) -> int:
        """Absolute brightness, 0-100."""
        return int(await self.set_value("brightness", str(value), source=source))

    async def adjust_brightness(self, delta: int, *, source: str | None = None) -> int:
        return int(await self.adjust_value("brightness", delta, source=source))

    async def get_contrast(self) -> int:
        return int(await self.get_value("contrast"))

    async def set_contrast(self, value: int, *, source: str | None = None) -> int:
        """Absolute contrast, 0-100."""
        return int(await self.set_value("contrast", str(value), source=source))

    async def get_video_freeze(self) -> bool:
        return _bool(await self.get_value("videofreeze"))

    async def set_video_freeze(self, enabled: bool) -> bool:
        return _bool(await self.set_value("videofreeze", _onoff(enabled)))

    async def get_closed_captioning(self) -> str:
        return await self.get_value("cc")

    async def set_closed_captioning(self, target: str) -> str:
        """One of ``"cc1"``, ``"cc2"``, or ``"off"``."""
        return await self.set_value("cc", target)

    # --- Audio controls ---------------------------------------------------

    async def get_volume(self) -> int:
        return int(await self.get_value("volume"))

    async def set_volume(self, value: int) -> int:
        """Absolute volume, -20 to 20."""
        return int(await self.set_value("volume", str(value)))

    async def adjust_volume(self, delta: int) -> int:
        return int(await self.adjust_value("volume", delta))

    async def get_mute(self) -> bool:
        return _bool(await self.get_value("mute"))

    async def mute_audio(self) -> bool:
        return _bool(await self.set_value("mute", "on"))

    async def unmute_audio(self) -> bool:
        return _bool(await self.set_value("mute", "off"))

    # --- Network controls ---------------------------------------------------

    async def get_network_status(self) -> str:
        """``"connected"``, ``"disconnected"``, or ``"disabled"``."""
        return await self.get_value("netstatus")

    async def get_ip_address(self) -> str:
        return await self.get_value("ipaddr")

    async def set_ip_address(self, value: str) -> str:
        return await self.set_value("ipaddr", value)

    async def get_mac_address(self) -> str:
        return await self.get_value("macaddr")

    async def get_network_enabled(self) -> bool:
        """The projector's network and VGA-out settings are off by default."""
        return _bool(await self.get_value("vgaoutnetenable"))

    async def enable_network(self) -> bool:
        return _bool(await self.set_value("vgaoutnetenable", "on"))

    async def disable_network(self) -> bool:
        return _bool(await self.set_value("vgaoutnetenable", "off"))

    # --- System info & controls ---------------------------------------------

    async def get_lamp_hours(self) -> int:
        return int(await self.get_value("lamphrs"))

    async def reset_lamp_hours(self) -> None:
        await self.transport.send_command("set lamphrs=0")

    async def get_system_hours(self) -> int:
        return int(await self.get_value("syshrs"))

    async def get_serial_number(self) -> str:
        return await self.get_value("serialnum")

    async def get_model_number(self) -> str:
        return await self.get_value("modelnum")

    async def restore_defaults(self) -> None:
        await self.transport.send_command("set restoredefaults")
