# smart-serial

Asyncio Python library for controlling SMART Technologies AV hardware
(starting with the **SMART UX60** projector) over a serial (RS-232)
connection. The driver layer is pluggable, so support for other models
or vendors can be added without touching this package's internals.

[![CI](https://github.com/jtjart/smart-serial/actions/workflows/ci.yml/badge.svg)](https://github.com/jtjart/smart-serial/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/smart-serial.svg)](https://pypi.org/project/smart-serial/)
[![Python versions](https://img.shields.io/pypi/pyversions/smart-serial.svg)](https://pypi.org/project/smart-serial/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

The SMART UX60 driver implements the RS-232 command set from Appendix B,
"Remotely managing your system through an RS-232 serial interface," of
SMART's SMART Board 600ix configuration and user's guide -- serial
settings, power state controls, source selection, display/audio/network
settings, and system commands. It hasn't yet been exercised against real
hardware; see [Verifying against real hardware](#verifying-against-real-hardware).

## Install

```bash
pip install smart-serial
```

Requires Python 3.10+.

## Quickstart

```python
import asyncio
from smart_serial import create_device


async def main() -> None:
    projector = create_device("smart", "ux60", "/dev/ttyUSB0")  # or "COM3" on Windows
    async with projector:  # connects on enter, disconnects on exit
        await projector.power_on()
        await projector.select_input("HDMI")
        print(await projector.get_power_state())


asyncio.run(main())
```

You can also import a driver class directly if you don't need the
registry lookup:

```python
from smart_serial import SerialTransport
from smart_serial.devices.smart.ux60 import SmartUX60

transport = SerialTransport("/dev/ttyUSB0")  # defaults to the UX60's 19200 baud
projector = SmartUX60(transport)
```

Every documented command is reachable, whether or not it has a
dedicated method, via the generic accessors:

```python
await projector.get_value("frequency")  # -> "0"
await projector.set_value("saturation", "80")  # -> "80"
await projector.adjust_value("brightness", -10)  # -> "45"
await projector.set_value("brightness", "65", source="vga1")  # target an inactive source
```

## Command-line interface

A small CLI is included for quick manual checks (`pip install` also
installs the `smart-serial` console script):

```bash
smart-serial --port /dev/ttyUSB0 power-state
smart-serial list-devices
```

## Architecture

```
smart_serial/
├── transport.py   # SerialTransport: async, prompt-delimited read/write over the port
├── device.py      # Device: abstract base class every driver extends
├── registry.py    # register() / create_device(): vendor:model -> Device class
└── devices/
    └── smart/
        └── ux60.py  # SmartUX60(Device): the actual command implementations
```

- **`SerialTransport`** owns the physical connection (via
  [`pyserial-asyncio-fast`](https://pypi.org/project/pyserial-asyncio-fast/))
  and knows nothing about any specific device. It speaks the
  command/prompt protocol common to this class of AV hardware: write a
  line, read until the device's next `>` prompt, hand back the reply.
  It paces writes with the ~10 ms inter-character delay the hardware
  guide calls for, and serializes access with a lock so concurrent
  callers don't interleave on the wire.
- **`Device`** is the abstract contract (`power_on`, `power_off`,
  `get_power_state`, connect/disconnect, async context manager) every
  driver implements.
- **`registry`** maps a `"vendor:model"` key to a `Device` subclass, so
  callers can do `create_device("smart", "ux60", port)` without
  importing the driver module directly.

## SMART UX60 driver reference

`SmartUX60` follows the `get <key>` / `set <key>=<value>` convention
used by almost every command in Appendix B, exposed generically via
`get_value()` / `set_value()` / `adjust_value()`, plus typed, ergonomic
wrappers for the commands you'll reach for most:

| Area | Wrapper methods |
| --- | --- |
| Power | `power_on`, `power_off`, `power_off_now`, `power_off_low_power`, `get_power_state` |
| Source | `get_input`, `select_input` |
| Display | `get_display_mode`/`set_display_mode`, `get_brightness`/`set_brightness`/`adjust_brightness`, `get_contrast`/`set_contrast`, `get_video_freeze`/`set_video_freeze`, `get_closed_captioning`/`set_closed_captioning` |
| Audio | `get_volume`/`set_volume`/`adjust_volume`, `get_mute`/`mute_audio`/`unmute_audio` |
| Network | `get_network_status`, `get_ip_address`/`set_ip_address`, `get_mac_address`, `get_network_enabled`/`enable_network`/`disable_network` |
| System | `get_lamp_hours`/`reset_lamp_hours`, `get_system_hours`, `get_serial_number`, `get_model_number`, `restore_defaults` |

Every other command in Appendix B (VGA tuning: `frequency`, `tracking`,
`saturation`, `tint`, `sharpness`; color: `red`/`green`/`blue`/`cyan`/
`magenta`/`yellow`; network: `dhcp`, `subnetmask`, `gateway`,
`primarydns`; system: `autosignal`, `lampreminder`, `highbrightness`,
`autopoweroff`, `zoom`, `projectorid`, `hposition`, `vposition`,
`aspectratio`, `projectionmode`, `startupscreen`, `language`,
`groupname`, `projectorname`, `locationinfo`, `contactinfo`,
`videomute`, `fwverddp`/`fwvernet`/`fwvermpu`/`fwverecp`,
`signaldetected`, `usb1source`/`usb2source`) works the same way through
`get_value()` / `set_value()` -- add a typed wrapper for any of these
following the pattern in `ux60.py` if you use one often.

**Serial settings:** 19200 baud, 8 data bits, no parity, 1 stop bit, no
flow control (the `SerialTransport` defaults already match this). The
projector's RS-232 port is a DCE device -- pin 2 = transmit, pin 3 =
receive, pin 5 = signal ground -- so a standard straight-through
male-to-female RS-232 cable is used, not a null-modem cable.

**Two-stage shutdown:** `power_off()` starts the shutdown sequence and
typically returns the `"Confirm off"` state; the projector requires a
*second* `power_off()` within 10 seconds to actually enter Standby.
Use `power_off_now()` to skip confirmation and shut down immediately
(this can't be cancelled or delayed).

**Network/VGA-out are off by default** on the projector itself --
`enable_network()` must be called (or set locally in the OSD) before
network-based control or VGA-out will work.

## Verifying against real hardware

Everything above is implemented directly from the vendor's documented
command reference (command keys, value ranges, response format, and
serial settings), but hasn't been run against a physical UX60 yet. Two
things are worth confirming with real hardware if you hit issues:

- **Response framing.** The transport reads until it sees a `>` prompt
  and returns the last non-empty line before it. The guide confirms a
  prompt follows every response but doesn't show raw byte sequences, so
  if your unit frames things differently, `SerialTransport.send_command`
  is the one place to adjust.
- **Inter-character timing.** The guide asks for a ~10 ms gap between
  characters "for reliable operation"; `SerialTransport` paces writes
  accordingly (`inter_character_delay`, tunable in the constructor) but
  hasn't been timing-verified on a real port.

If you confirm either of these against hardware, a PR updating this
section (and removing the caveat) would be very welcome.

## Adding support for another model

You don't need to fork this repository to add a device. Two options:

**1. Contribute a driver directly to this package** (good for models
closely related to what's already here):

1. Create `src/smart_serial/devices/<vendor>/<model>.py` with a class
   that extends `Device`, sets `vendor`/`model`, and is decorated with
   `@register`. Use `devices/smart/ux60.py` as a template -- if the new
   model shares SMART's `get`/`set` key=value convention, its
   `get_value`/`set_value`/`adjust_value` implementation can likely be
   copied directly.
2. Import it from `src/smart_serial/devices/__init__.py`.
3. Add a matching line under `[project.entry-points."smart_serial.devices"]`
   in `pyproject.toml`.
4. Add tests under `tests/`, following `test_ux60.py` and the
   `fake_transport` fixture in `tests/conftest.py` (no real hardware
   needed).

**2. Publish a separate plugin package** (good for third-party/private
models, or models you don't want bundled here): add this to your own
package's `pyproject.toml`, with no dependency on this repo's source:

```toml
[project.entry-points."smart_serial.devices"]
"acme:projector-9000" = "acme_smart_serial.driver:AcmeProjector9000"
```

Once both packages are installed, `smart_serial.available_devices()`
and `create_device()` pick it up automatically.

## Development

```bash
git clone https://github.com/jtjart/smart-serial.git
cd smart-serial
python -m venv .venv
source .venv/bin/activate  # .venv\Scripts\activate on Windows
pip install -e ".[dev]"
pre-commit install
```

Run the checks locally the same way CI does:

```bash
ruff check .
ruff format --check .
mypy src
pytest --cov=smart_serial
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full development
workflow, and [.vscode/](.vscode/) for editor integration --
recommended extensions, debugging, and test discovery are pre-configured
there (see `.vscode/extensions.json`).

## License

MIT -- see [LICENSE](LICENSE). Not affiliated with or endorsed by SMART
Technologies ULC; "SMART" and "SMART Board" are trademarks of their
respective owner, referenced here only to describe hardware
compatibility.
