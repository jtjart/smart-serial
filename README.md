# smart-serial

Asyncio Python library for controlling SMART Technologies AV hardware
(starting with the **SMART UX60** projector) over a serial (RS-232)
connection. Devices are implemented as explicit subclasses of `Device`,
so you import the model you want and use it directly.

[![CI](https://github.com/jtjart/smart-serial/actions/workflows/ci.yml/badge.svg)](https://github.com/jtjart/smart-serial/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/smart-serial.svg)](https://pypi.org/project/smart-serial/)
[![Python versions](https://img.shields.io/pypi/pyversions/smart-serial.svg)](https://pypi.org/project/smart-serial/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

The SMART UX60 driver implements the RS-232 command set from Appendix B,
"Remotely managing your system through an RS-232 serial interface," of
SMART's SMART Board 600ix configuration and user's guide -- serial
settings, power state controls, source selection, display/audio/network
settings, and system commands.

The transport follows the projector's operating notes closely:

- send a command only after the device has emitted the next `>` prompt
- keep roughly 10 ms between characters when writing to the port
- type commands exactly as documented and press Enter after each one
- wait for the device's response before sending the next command

## Install

```bash
pip install smart-serial
```

Requires Python 3.11+.

## Quickstart

```python
import asyncio

from smart_serial.devices.smart.ux60 import SmartUX60


async def main() -> None:
    projector = SmartUX60.create("/dev/ttyUSB0")  # or "COM3" on Windows
    async with projector:  # connects on enter, disconnects on exit
        await projector.power_on()
        await projector.select_input("HDMI")
        print(await projector.get_power_state())


asyncio.run(main())
```

You can also instantiate the transport manually and pass it in:

```python
from smart_serial import SerialTransport
from smart_serial.devices.smart.ux60 import SmartUX60

transport = SerialTransport("/dev/ttyUSB0")  # defaults to the UX60's 19200 baud
projector = SmartUX60(transport)
```

The library intentionally does not expose a dynamic registry lookup; you
choose the concrete device class explicitly.

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
```

## Architecture

```
smart_serial/
├── transport.py   # SerialTransport: async, prompt-delimited read/write over the port
├── device.py      # Device: abstract base class every driver extends
├── devices/
│   └── smart/
│       └── ux60.py  # SmartUX60(Device): the actual command implementations
└── cli.py         # small CLI for manual testing against the built-in device
```

- **`SerialTransport`** owns the physical connection (via
  [`pyserial-asyncio-fast`](https://pypi.org/project/pyserial-asyncio-fast/))
  and knows nothing about any specific device. It speaks the
  command/prompt protocol common to this class of AV hardware: only send
  a command after the projector has issued the ready `>` prompt, write a
  line, then read until the device's next `>` prompt and return the
  reply. It paces writes with the ~10 ms inter-character delay the
  hardware guide calls for, and serializes access with a lock so
  concurrent callers don't interleave on the wire.
- **`Device`** is the abstract contract (`power_on`, `power_off`,
  `get_power_state`, connect/disconnect, async context manager) every
  driver implements.
- **Built-in devices** are normal Python classes that live under
  `smart_serial.devices`; callers import the concrete class they need
  rather than relying on a runtime registry lookup.

## Development

Development is done in the Python 3.13 dev container. See
[CONTRIBUTING.md](CONTRIBUTING.md) for setup and the development workflow.

## License

MIT -- see [LICENSE](LICENSE). Not affiliated with or endorsed by SMART
Technologies ULC; "SMART" and "SMART Board" are trademarks of their
respective owner, referenced here only to describe hardware
compatibility.
