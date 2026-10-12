# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed
- A connection reset while stale bytes were being discarded before a write escaped as a raw
  `ConnectionResetError`; it is now a `ConnectionLostError`.
- Writing to a connection the peer had already dropped made asyncio log
  `socket.send() raised exception.` once per remaining character. The write now stops
  immediately and raises `ConnectionLostError`.
- `SerialTransport.connect()` is safe to call concurrently; the port is opened only once.

## [0.3.0] - 2026-09-20

### Fixed
- `SmartUX60.create(...)` and `async with SmartUX60.create(...) as d` now return `SmartUX60`
  (via `typing.Self`), not `Device`, so editors and type checkers offer the full API.
- A timeout no longer causes a blind re-send of every command. Only idempotent commands
  (`get`, absolute `set`, `on`) are retried after a timeout. `off` and relative adjustments
  (`set volume+5`) are not: re-sending `off` was read by the projector as the shutdown
  confirmation, and re-sending `+5` could apply it twice. A *garbled* command
  (`invalid cmd=<something else>`) is still always re-sent, because it was not executed.
- EOF on the serial port (e.g. USB adapter unplugged) raises `ConnectionLostError` and marks
  the transport disconnected, instead of being retried as a timeout.
- Failing to open the port raises `ConnectionFailedError` (a `SmartSerialError`) instead of
  a bare `OSError`.
- Stale bytes are drained only after connect or after a failed exchange, no longer before
  *every* command (which added ~50 ms to each one).
- `smart-serial power-off` now actually powers off (it used to stop at "Confirm off").
  The CLI prints the resulting state, reports library errors as `error: ...` with exit
  code 1, and `--port` is properly required.
- Boolean replies are parsed strictly: an unrecognised reply raises `UnexpectedResponseError`
  instead of silently becoming `False`. Bad enum / integer / IP replies raise
  `UnexpectedResponseError` instead of a raw `ValueError`.
- `DeviceIdleError` is only raised when the projector confirms `powerstate=Idle`. A command
  rejected for another reason (e.g. a VGA-only setting while on HDMI) raises
  `CommandRejectedError`. `str(DeviceIdleError)` now shows the idle message.
- A string value containing a line break can no longer smuggle a second command onto the wire.
- `Source("VGA 1")` and `Source("vga1")` are now equal; `display_name` no longer produces
  `"Vga  1"`. `Source` is immutable (it was hashable but mutable) and has a useful `repr`.
- Enum replies are matched case-insensitively.

### Added
- `SmartDevice` base class (`smart_serial.devices.base`) implementing SMART's
  `get`/`set` console protocol once; new SMART models only declare their settings.
- Declarative, typed settings (`IntSetting`, `AdjustableIntSetting`, `BoolSetting`,
  `EnumSetting`, `StrSetting`, `IPv4Setting`, `Setting`, `ReadOnlySetting`), with metadata
  (`bounds`, `enum`, `max_length`, `per_source`, `doc`) and `SmartDevice.settings()` for
  introspection by generic integrations.
- `PowerControl` capability protocol (`turn_on()`, `turn_off()`, `is_on()`), implemented by
  `SmartUX60`.
- `SerialSettings` dataclass (line settings and framing); `Transport` protocol.
- `Source.coerce()`; `select_input()` and the `source=` arguments accept plain strings.
- `CommandRejectedError`, `UnexpectedResponseError`, `ConnectionLostError`,
  `ConnectionFailedError`.

### Changed (breaking)
- **Settings are attributes instead of `get_x`/`set_x`/`adjust_x` methods.**
  `await p.get_brightness()` -> `await p.brightness.get()`; `set_x(v)` -> `.set(v)`;
  `adjust_x(n)` -> `.adjust(n)` (only for the settings that had `adjust_x` before).
  Renames: `whitepeaking` -> `white_peaking`, `hposition` -> `horizontal_position`,
  `vposition` -> `vertical_position`, `usb1source`/`usb2source` -> `usb1_source`/`usb2_source`.
  Unchanged: `get_value`, `set_value`, `adjust_value`, `power_on`, `power_off`, `power_off_now`,
  `power_off_low_power`, `get_power_state`, `get_input`, `select_input`, `get_video_inputs`,
  `restore_defaults`, `reset_lamp_hours`.
- `Device.create(port, **kwargs)` -> `Device.create(port, settings: SerialSettings | None = None)`.
  `SerialTransport(port, baudrate=...)` -> `SerialTransport(port, SerialSettings(baudrate=...))`.
  `Device.default_baudrate` -> `Device.serial_settings`.
- `SerialTransport.send_command()` (returned one parsed line, retried internally) ->
  `SerialTransport.exchange()` (returns the raw text before the prompt). Reply parsing and
  retries moved to `SmartDevice`.
- `Device` no longer declares abstract `power_on`/`power_off`/`get_power_state`; use the
  `PowerControl` protocol for generic code.
- `smart_serial.utils.source.Source` moved to `smart_serial.source.Source`.
- `DeviceIdleError` now derives from `CommandRejectedError`; its `.message` attribute is gone
  (use `str(exc)`).

### Removed
- `set_int_value()` and the `*_range` class attributes; use e.g. `SmartUX60.brightness.bounds`.

## [0.2.0] - 2026-09-18

### Changed

- Added a Python 3.13 development container and standardized local tooling
  on `uv` dependency groups and `uv run` commands.
- Simplified the public API to explicit device imports instead of a
  dynamic registry/plugin lookup, matching the repository's intended
  model of direct per-device classes.
- Removed the pluggable registry layer and entry-point metadata from the
  package surface.
- Clarified the project’s architecture and documentation to emphasize
  importing `SmartUX60` directly and constructing it via `Device.create()`
  or a custom `SerialTransport`.
- Hardened the serial transport to enforce the projector protocol
  notes: it now drains a pending prompt before sending a new command and
  maintains the required ~10 ms inter-character delay while writing.
- Added transport-level tests covering prompt-before-write behavior,
  retry logic, and command-response parsing.
- Added `get_video_inputs()` method to the `SmartUX60` driver to get
  available video input sources.
- Added many `get_`/`set_`/`adjust_` accessors for the UX60 driver to cover all
  documented commands.
- Fixed the serial write flow to respect the SMART projector’s requirement
  that new commands are only issued after the ready prompt has been seen.
- Improved reliability for prompt-based command handling by treating the
  next `>` prompt as the gate for the next outgoing command.

## [0.1.0] - 2026-08-28

### Added

- Initial project scaffold: `SerialTransport` (async, prompt-delimited
  RS-232 I/O paced with the hardware's ~10 ms inter-character delay),
  `Device` abstract base class, and a pluggable `registry` supporting
  both built-in and third-party (entry-point based) drivers.
- `SmartUX60` driver implementing the RS-232 command set from Appendix
  B of SMART's SMART Board 600ix configuration and user's guide: power
  state controls (including the two-stage shutdown confirmation),
  source selection, display/color/audio settings, network controls,
  and system commands, plus generic `get_value`/`set_value`/
  `adjust_value` accessors covering every documented command.
- Minimal `smart-serial` CLI for manual testing.
- Test suite (`pytest` + `pytest-asyncio`) covering the registry, the
  UX60 driver (via a fake transport), and the real serial transport's
  connect/disconnect lifecycle (via pySerial's `loop://` virtual port).
- Development tooling: `ruff` (lint + format), `mypy` (strict), `pytest`
  with coverage, `pre-commit`, GitHub Actions CI, and a trusted-publishing
  release workflow.
