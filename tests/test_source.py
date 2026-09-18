from smart_serial.utils.source import Source


def test_source_normalizes_case() -> None:
    assert Source("HDMI1").value == "hdmi1"
    assert Source("HdMi2").value == "hdmi2"


def test_source_strips_whitespace() -> None:
    assert Source("  HDMI1  ").value == "hdmi1"


def test_sources_with_same_value_are_equal() -> None:
    assert Source("hdmi") == Source("hdmi")


def test_source_equality_is_case_insensitive() -> None:
    assert Source("HDMI") == Source("hdmi")


def test_different_sources_are_not_equal() -> None:
    assert Source("hdmi1") != Source("hdmi2")


def test_display_name_with_number() -> None:
    assert Source("hdmi1").display_name == "HDMI 1"


def test_display_name_without_number() -> None:
    assert Source("vga").display_name == "VGA"


def test_display_name_with_special_name() -> None:
    assert Source("s-video1").display_name == "S-Video 1"


def test_unknown_source() -> None:
    source = Source("network1")

    assert source.value == "network1"
    assert source.display_name == "Network 1"


def test_source_can_be_used_in_set() -> None:
    sources = {Source("HDMI1"), Source("hdmi1")}

    assert len(sources) == 1
