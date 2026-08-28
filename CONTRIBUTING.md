# Contributing

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # .venv\Scripts\activate on Windows
pip install -e ".[dev]"
pre-commit install
```

## Workflow

1. Create a branch off `main`.
2. Make your change, with tests. Driver changes go in
   `src/smart_serial/devices/<vendor>/<model>.py` with matching tests in
   `tests/`; see `devices/smart/ux60.py` / `tests/test_ux60.py` as the
   template.
3. Run the full check suite locally before pushing:

   ```bash
   ruff check .
   ruff format .
   mypy src
   pytest --cov=smart_serial --cov-report=term-missing
   ```

   (`pre-commit run --all-files` runs the lint/format hooks in one go.)
4. Update `CHANGELOG.md` under an "Unreleased" heading.
5. Open a PR. CI (`.github/workflows/ci.yml`) runs the same checks
   across the supported Python versions.

## Commit style

Plain, descriptive commit messages are fine -- no enforced convention.
Keep commits focused; it's fine to have several small commits in a PR.

## Adding a new device driver

See the "Adding support for another model" section of the
[README](README.md#adding-support-for-another-model). In short: extend
`Device`, register it, add it to `devices/__init__.py` and to the
`[project.entry-points."smart_serial.devices"]` table in
`pyproject.toml`, and add tests using the `fake_transport` fixture from
`tests/conftest.py` so no real hardware is needed to test your driver's
command formatting.

## Releasing

Releases are built and published to PyPI automatically by
`.github/workflows/release.yml` whenever a GitHub Release is published,
using PyPI's
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (OIDC) --
no API token needs to be stored as a repo secret. To cut a release:

1. Bump `__version__` in `src/smart_serial/__init__.py`.
2. Move the "Unreleased" section of `CHANGELOG.md` under a new version
   heading.
3. Commit, tag (`git tag vX.Y.Z`), push the tag, and publish a GitHub
   Release from it.
4. The `release.yml` workflow builds the sdist/wheel and uploads them to
   PyPI.

The PyPI project must be configured to trust this workflow first -- see
the repository's own setup notes in the pull request/issue tracker, or
PyPI's Trusted Publishing docs linked above, for the one-time setup.
