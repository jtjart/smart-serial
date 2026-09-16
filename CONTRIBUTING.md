# Contributing

## Setup

Open the repository in the dev container using VS Code and the Dev Containers
extension. The container's `postCreateCommand` installs the development
dependencies and pre-commit hooks automatically.

The container is defined in
[`.devcontainer/devcontainer.json`](.devcontainer/devcontainer.json).

## Workflow

1. Create a branch off `main`.
2. Make your change, with tests. Driver changes go in
   `src/smart_serial/devices/<vendor>/<model>.py` with matching tests in
   `tests/`; see `devices/smart/ux60.py` / `tests/test_ux60.py` as the
   template.
3. Run the full check suite locally before pushing:

   ```bash
   uv run ruff check .
   uv run ruff format --check .
   uv run mypy src
   uv run pyright
   uv run pytest --cov=smart_serial --cov-report=term-missing
   ```

   (`uv run pre-commit run --all-files` runs the configured hooks in one go.)
4. Update `CHANGELOG.md` under an "Unreleased" heading.
5. Open a PR. CI (`.github/workflows/ci.yml`) runs the same checks
   across the supported Python versions.

## Commit style

Plain, descriptive commit messages are fine -- no enforced convention.
Keep commits focused; it's fine to have several small commits in a PR.

## Adding a new device driver

See the "Adding support for another model" section of the
[README](README.md#adding-support-for-another-model). In short: extend
`Device`, add the driver under `src/smart_serial/devices/`, import it from
`devices/__init__.py`, and add tests using the `fake_transport` fixture from
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
