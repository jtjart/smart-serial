# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

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
