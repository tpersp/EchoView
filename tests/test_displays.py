from copy import deepcopy
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from echoview import displays

FIXTURE = Path(__file__).parent / "fixtures/displays/xrandr.txt"


def inventory():
    return displays.parse_xrandr(FIXTURE.read_text())


def test_composite_no_edid_negative_position_and_disconnected_boundaries():
    found = inventory()
    assert found["Composite-1"]["kind"] == "composite"
    assert found["Composite-1"]["model"] is None
    assert (found["Composite-1"]["x"], found["Composite-1"]["y"]) == (-720, 24)
    assert found["Composite-1"]["current_mode"] == "720x576i"
    assert found["Composite-1"]["current_rate"] == "50.00"
    assert found["HDMI-2"]["modes"] == ["640x480"]
    assert "640x480" not in found["Composite-1"]["modes"]
    assert found["DSI-1"]["connected"] and not found["DSI-1"]["active"]
    assert displays.mode_choices(found["Composite-1"])[0]["value"] == "720x576i@50.00"


def test_edid_name_is_optional_and_decoded_when_present():
    edid = bytearray(128)
    edid[54:72] = b"\x00\x00\x00\xfc\x00" + b"CRT fixture\n ".ljust(13)
    lines = "HDMI-1 connected 640x480+0+0\n\tEDID:\n" + "\n".join("\t\t" + edid[i:i+16].hex() for i in range(0, 128, 16))
    assert displays.parse_xrandr(lines)["HDMI-1"]["model"] == "CRT fixture"


def test_discovery_timeout_is_bounded_and_does_not_delete_config(monkeypatch):
    def timeout(*args, **kwargs):
        assert kwargs["timeout"] == 5
        raise subprocess.TimeoutExpired(args[0], 5)
    monkeypatch.setattr(displays.subprocess, "run", timeout)
    assert displays.discover_monitors() == {}
    cfg = {"displays": {"HDMI-1": {"specific_image": "keep.png"}}}
    assert displays.reconcile_displays(cfg, {}) is False
    assert cfg["displays"]["HDMI-1"]["specific_image"] == "keep.png"


def test_reconcile_preserves_offline_settings_and_unique_alias():
    cfg = {"displays": {"HDMI-A-1": {"specific_image": "keep.png"}, "TV-9": {"mode": "spotify"}}}
    displays.reconcile_displays(cfg, inventory())
    assert "HDMI-A-1" not in cfg["displays"]
    assert cfg["displays"]["HDMI-1"]["specific_image"] == "keep.png"
    assert cfg["displays"]["TV-9"] == {"mode": "spotify"}
    assert cfg["displays"]["Composite-1"]["output_mode"] == "auto"
    assert displays.reconcile_displays(cfg, inventory()) is False


def test_only_unambiguous_legacy_placeholder_is_migrated():
    cfg = {"displays": {"Display0": {"mode": "spotify"}}}
    displays.reconcile_displays(cfg, {"Composite-1": inventory()["Composite-1"]})
    assert set(cfg["displays"]) == {"Composite-1"}
    assert cfg["displays"]["Composite-1"]["mode"] == "spotify"
    cfg = {"displays": {"Display0": {"mode": "spotify"}}}
    displays.reconcile_displays(cfg, inventory())
    assert cfg["displays"]["Display0"]["mode"] == "spotify"


def test_screen_assignment_uses_identity_not_list_order():
    cfg = {"displays": {"HDMI-A-1": {}, "Composite-1": {}, "HDMI-9": {}}}
    hdmi = SimpleNamespace(name=lambda: "HDMI-1")
    composite = SimpleNamespace(name=lambda: "Composite-1")
    for screens in ([composite, hdmi], [hdmi, composite]):
        assert displays.screen_assignments(cfg, screens) == [("HDMI-A-1", hdmi), ("Composite-1", composite)]
    assert displays.screen_assignments(cfg, [composite]) == [("Composite-1", composite)]


def test_verified_mode_application_uses_argument_array():
    original = inventory()
    actual = deepcopy(original)
    actual["HDMI-1"].update(current_mode="1280x720", current_rate="60.00")
    sequence = iter([original, actual])
    commands = []
    def run(args, **kwargs):
        assert kwargs["timeout"] == 5 and kwargs["check"]
        commands.append(args)
    result = displays.apply_output_mode("HDMI-1", "1280x720@60.00", discover=lambda: next(sequence), runner=run)
    assert result["current_mode"] == "1280x720"
    assert commands == [["xrandr", "--output", "HDMI-1", "--mode", "1280x720", "--rate", "60.00"]]


def test_failed_mode_verification_requests_rollback():
    calls = []
    with pytest.raises(ValueError, match="previous mode"):
        displays.apply_output_mode("HDMI-1", "1280x720@60.00", discover=inventory,
                                   runner=lambda args, **kwargs: calls.append(args))
    assert calls[-1] == ["xrandr", "--output", "HDMI-1", "--mode", "1920x1080", "--rate", "60.00"]


def test_mode_and_rollback_failures_are_reported():
    def fail(*args, **kwargs):
        raise OSError("unavailable")
    with pytest.raises(RuntimeError, match="rollback failed"):
        displays.apply_output_mode("HDMI-1", "1280x720@60.00", discover=inventory, runner=fail)


@pytest.mark.parametrize("name,selection", [("Composite-1", "1920x1080@60.00"), ("HDMI-2", "auto"), ("HDMI-1", "1920x1080;touch /tmp/unsafe")])
def test_unadvertised_disconnected_and_injected_modes_never_run(name, selection):
    with pytest.raises(ValueError):
        displays.apply_output_mode(name, selection, discover=inventory,
                                   runner=lambda *args, **kwargs: pytest.fail("command executed"))


def test_auto_activates_a_connected_inactive_output():
    original, actual = inventory(), inventory()
    actual["DSI-1"].update(active=True, current_mode="800x480", current_rate="60.00")
    sequence = iter([original, actual])
    calls = []
    displays.apply_output_mode("DSI-1", "auto", discover=lambda: next(sequence), runner=lambda args, **kwargs: calls.append(args))
    assert calls == [["xrandr", "--output", "DSI-1", "--auto"]]


@pytest.mark.parametrize("raster,aspect", [((720, 576), "4:3"), ((720, 480), "4:3"), ((1920, 1080), "16:9"), ((1920, 1080), "4:3"), ((1280, 1024), "1:1")])
def test_square_art_retains_physical_shape(raster, aspect):
    width, height = raster
    pixel = displays.display_pixel_aspect(aspect, width, height)
    art_w, art_h = displays.fit_dimensions(1000, 1000, width, height, pixel)
    assert art_w <= width and art_h <= height
    assert art_w / art_h * pixel == pytest.approx(1, abs=0.003)


def test_auto_aspect_uses_composite_four_three_and_square_hdmi_pixels():
    assert displays.display_pixel_aspect("auto", 720, 576, "Composite-1") == pytest.approx(16 / 15)
    assert displays.display_pixel_aspect("auto", 720, 480, "TV-1") == pytest.approx(8 / 9)
    assert displays.display_pixel_aspect("auto", 1920, 1080, "HDMI-1") == 1


def test_duplicate_qt_names_are_not_assigned_arbitrarily():
    first = SimpleNamespace(name=lambda: "HDMI-1")
    second = SimpleNamespace(name=lambda: "HDMI-1")
    assert displays.screen_assignments({"displays": {"HDMI-1": {}}}, [first, second]) == []


def test_exact_screen_identity_is_reserved_before_aliases():
    screen = SimpleNamespace(name=lambda: "HDMI-1")
    cfg = {"displays": {"HDMI-A-1": {}, "HDMI-1": {}}}
    assert displays.screen_assignments(cfg, [screen]) == [("HDMI-1", screen)]
