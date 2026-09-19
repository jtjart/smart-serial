from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from smart_serial import SerialSettings, SerialTimeoutError, SmartUX60
from smart_serial.cli import main

if TYPE_CHECKING:
    from conftest import FakeTransport


@pytest.fixture
def created_with(
    monkeypatch: pytest.MonkeyPatch, fake: FakeTransport
) -> list[tuple[str, SerialSettings]]:
    """Make SmartUX60.create() return a device on the fake transport; record its arguments."""
    calls: list[tuple[str, SerialSettings]] = []

    def create(
        cls: type[SmartUX60], port: str, settings: SerialSettings | None = None
    ) -> SmartUX60:
        assert settings is not None
        calls.append((port, settings))
        return cls(fake)

    monkeypatch.setattr(SmartUX60, "create", classmethod(create))
    return calls


def test_power_state(
    fake: FakeTransport,
    created_with: list[tuple[str, SerialSettings]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake.queue("powerstate=On")
    assert main(["--port", "/dev/ttyUSB0", "power-state"]) == 0
    assert capsys.readouterr().out.strip() == "On"
    assert created_with[0][0] == "/dev/ttyUSB0"
    assert created_with[0][1].baudrate == 19200
    assert fake.connect_calls == 1
    assert fake.disconnect_calls == 1


def test_power_on_prints_the_resulting_state(
    fake: FakeTransport,
    created_with: list[tuple[str, SerialSettings]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake.queue("powerstate=Powering")
    assert main(["--port", "x", "power-on"]) == 0
    assert capsys.readouterr().out.strip() == "Powering"
    assert fake.sent == ["on"]


def test_power_off_actually_powers_off(
    fake: FakeTransport,
    created_with: list[tuple[str, SerialSettings]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The old CLI sent one 'off' and stopped at the 'Confirm off' prompt."""
    fake.queue("powerstate=Cooling", "powerstate=Cooling")
    assert main(["--port", "x", "power-off"]) == 0
    assert fake.sent == ["off now", "get powerstate"]
    assert capsys.readouterr().out.strip() == "Cooling"


def test_baudrate_override(
    fake: FakeTransport, created_with: list[tuple[str, SerialSettings]]
) -> None:
    fake.queue("powerstate=On")
    main(["--port", "x", "--baudrate", "9600", "power-state"])
    assert created_with[0][1].baudrate == 9600
    assert SmartUX60.serial_settings.baudrate == 19200


def test_library_errors_become_a_message_and_exit_code_1(
    fake: FakeTransport,
    created_with: list[tuple[str, SerialSettings]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake.queue(*[SerialTimeoutError("x", "get powerstate")] * 3)
    assert main(["--port", "x", "power-state"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error: Timed out")
    assert fake.disconnect_calls == 1


def test_port_is_required() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["power-state"])
    assert excinfo.value.code == 2
