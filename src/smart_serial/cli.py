"""Minimal command-line interface for quick manual testing against real hardware.

This is intentionally small -- a way to poke a device from a terminal
while wiring things up, not a full control surface. Use the library
directly from your own asyncio code for anything more than that; see
the README for examples.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from .registry import available_devices, create_device


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smart-serial",
        description="Send a single command to a serial-controlled AV device.",
    )
    parser.add_argument("--port", help="Serial port, e.g. /dev/ttyUSB0 or COM3")
    parser.add_argument("--vendor", default="smart", help="Device vendor key (default: smart)")
    parser.add_argument("--model", default="ux60", help="Device model key (default: ux60)")
    parser.add_argument("--baudrate", type=int, default=None, help="Override the default baud rate")
    parser.add_argument(
        "action",
        choices=["power-on", "power-off", "power-state", "list-devices"],
        help="Action to perform",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    if args.action == "list-devices":
        for key in available_devices():
            print(key)
        return 0

    if not args.port:
        print("error: --port is required for this action", file=sys.stderr)
        return 2

    kwargs: dict[str, object] = {} if args.baudrate is None else {"baudrate": args.baudrate}
    device = create_device(args.vendor, args.model, args.port, **kwargs)
    async with device:
        if args.action == "power-on":
            await device.power_on()
        elif args.action == "power-off":
            await device.power_off()
        elif args.action == "power-state":
            print(await device.get_power_state())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
