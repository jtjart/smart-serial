"""Minimal command-line interface for quick manual testing against real hardware.

This is intentionally small -- a way to poke a device from a terminal
while wiring things up, not a full control surface. Use the library
directly from your own asyncio code for anything more than that; see
the README for examples.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import sys

from .devices.ux60 import SmartUX60
from .exceptions import SmartSerialError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smart-serial",
        description="Send a single command to a SMART UX60 projector.",
    )
    parser.add_argument("--port", required=True, help="Serial port, e.g. /dev/ttyUSB0 or COM3")
    parser.add_argument("--baudrate", type=int, default=None, help="Override the default baud rate")
    parser.add_argument(
        "action",
        choices=["power-on", "power-off", "power-state"],
        help="Action to perform",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    settings = SmartUX60.serial_settings
    if args.baudrate is not None:
        settings = dataclasses.replace(settings, baudrate=args.baudrate)

    device = SmartUX60.create(args.port, settings)
    try:
        async with device:
            if args.action == "power-on":
                state = await device.power_on()
            elif args.action == "power-off":
                # turn_off() answers the projector's "Confirm off" prompt; a bare
                # power_off() would only start the shutdown sequence.
                await device.turn_off()
                state = await device.get_power_state()
            else:
                state = await device.get_power_state()
    except SmartSerialError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(state)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
