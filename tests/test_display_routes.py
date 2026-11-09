from copy import deepcopy
from pathlib import Path
import subprocess

from flask import Flask
import pytest

from echoview import displays, utils
from echoview.web import routes


@pytest.fixture
def controller(monkeypatch):
    found = displays.parse_xrandr((Path(__file__).parent / "fixtures/displays/xrandr.txt").read_text())
    cfg = {"displays": {"Composite-1": dict(displays.default_display("Composite-1"), chosen_mode="1920x1080"),
                        "HDMI-9": dict(displays.default_display("HDMI-9"), specific_image="saved.png")}}
    saved, applied = [], []
    monkeypatch.setattr(routes, "load_config", lambda: cfg)
    monkeypatch.setattr(routes, "save_config", lambda new: saved.append(deepcopy(new)))
    monkeypatch.setattr(routes, "discover_monitors", lambda: found)
    monkeypatch.setattr(routes, "apply_output_mode", lambda name, selection: applied.append((name, selection)))
    monkeypatch.setattr(routes, "get_system_stats", lambda: (0, 0, 0, 0, "unknown"))
    monkeypatch.setattr(routes, "get_storage_stats", lambda: (0, 0))
    monkeypatch.setattr(routes, "get_hostname", lambda: "fixture")
    monkeypatch.setattr(routes, "get_ip_address", lambda: "fixture")
    monkeypatch.setattr(routes, "get_pi_model", lambda: "fixture")
    monkeypatch.setattr(routes, "get_subfolders", lambda: [])
    monkeypatch.setattr(routes.subprocess, "run", lambda *args, **kwargs: None)
    app = Flask("echoview.web.app", template_folder="templates", static_folder="static")
    app.secret_key = "test"
    app.register_blueprint(routes.main_bp)
    return app.test_client(), cfg, found, saved, applied


def test_actual_modes_and_offline_preferences_are_distinct(controller):
    client, cfg, found, saved, applied = controller
    response = client.get("/")
    assert response.status_code == 200
    assert b"Actual: 720x576i @ 50.00 Hz" in response.data
    assert b"Saved preference: auto" in response.data
    assert b"HDMI-9" in response.data and b"Disconnected / unavailable" in response.data
    assert cfg["displays"]["HDMI-9"]["specific_image"] == "saved.png"
    assert applied == []  # Viewing the page must never change hardware modes.


def test_list_monitors_uses_actual_connector_data(controller):
    client, cfg, found, saved, applied = controller
    response = client.get("/list_monitors")
    data = response.get_json()
    assert data["Composite-1"]["offset_x"] == -720
    assert data["Composite-1"]["resolution"] == "720x576i"
    assert data["Composite-1"]["available_modes"][0]["value"] == "720x576i@50.00"
    assert data["HDMI-2"]["connected"] is False
    assert "Display0" not in data


def test_output_preferences_saved_only_after_success(controller):
    client, cfg, found, saved, applied = controller
    response = client.post("/display/output", data={"display": "Composite-1", "output_mode": "720x576i@50.00", "display_aspect": "4:3"})
    assert response.status_code == 302
    assert applied == [("Composite-1", "720x576i@50.00")]
    assert saved[-1]["displays"]["Composite-1"]["display_aspect"] == "4:3"
    assert saved[-1]["displays"]["Composite-1"]["output_mode"] == "720x576i@50.00"


def test_failed_mode_change_does_not_save_new_preferences(controller, monkeypatch):
    client, cfg, found, saved, applied = controller
    before = deepcopy(cfg)
    def fail(*args):
        raise ValueError("Mode unavailable")
    monkeypatch.setattr(routes, "apply_output_mode", fail)
    assert client.post("/display/output", data={"display": "Composite-1", "output_mode": "1920x1080@60.00", "display_aspect": "16:9"}).status_code == 400
    assert not saved and cfg == before


def test_invalid_aspect_and_unknown_display_never_change_output(controller):
    client, cfg, found, saved, applied = controller
    for data in ({"display": "Composite-1", "display_aspect": "invalid"}, {"display": "unknown"}):
        assert client.post("/display/output", data=data).status_code == 400
    assert not saved and not applied


def test_saved_settings_and_restart_failure_reported_separately(controller, monkeypatch):
    client, cfg, found, saved, applied = controller
    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired("systemctl", 10)
    monkeypatch.setattr(routes.subprocess, "run", fail)
    client.post("/display/output", data={"display": "Composite-1", "display_aspect": "4:3"})
    response = client.get("/")
    assert b"restart the viewer" in response.data
    assert saved[-1]["displays"]["Composite-1"]["display_aspect"] == "4:3"


def test_migration_does_not_activate_legacy_display_only_resolution():
    cfg = {"displays": {"HDMI-1": {"chosen_mode": "1920x1080"}}}
    utils.upgrade_config(cfg)
    assert cfg["displays"]["HDMI-1"]["chosen_mode"] == "1920x1080"
    assert cfg["displays"]["HDMI-1"]["output_mode"] == "auto"


def test_presentation_controls_do_not_change_output_mode(controller):
    client, cfg, found, saved, applied = controller
    response = client.post("/display/presentation", data={"display": "HDMI-9", "safe_left": "5", "safe_bottom": "7.5", "resource_profile": "pi3"})
    assert response.status_code == 302
    assert not applied  # Safe-area settings also work while the output is offline.
    result = saved[-1]["displays"]["HDMI-9"]
    assert result["safe_area"] == {"left": 5, "right": 0, "top": 0, "bottom": 7.5}
    assert "resource_profile" not in result
    assert result["output_mode"] == "auto" and result["specific_image"] == "saved.png"


@pytest.mark.parametrize("data", [{"safe_top": "nan"}, {"safe_right": "-1"}, {"safe_bottom": "21"}])
def test_invalid_presentation_input_does_not_save_or_apply(controller, data):
    client, cfg, found, saved, applied = controller
    before = deepcopy(cfg)
    response = client.post("/display/presentation", data={"display": "Composite-1", **data})
    assert response.status_code == 400
    assert not saved and not applied and cfg == before


def test_presentation_page_explains_gif_tradeoff_and_calibration(controller):
    client, cfg, found, saved, applied = controller
    response = client.get("/")
    assert response.status_code == 200
    assert b'name="resource_profile"' not in response.data
    assert b"Calibration Pattern" in response.data
    assert b'name="safe_left"' in response.data


def test_invalid_clock_font_size_is_rejected_without_saving(controller):
    client, cfg, found, saved, applied = controller
    response = client.post("/overlay_config", data={"Composite-1_clock_font_size": "nan"})
    assert response.status_code == 400
    assert not saved


def test_youtube_fallback_is_real_http_page_with_referer_origin(controller):
    from urllib.parse import parse_qs, urlparse
    from html.parser import HTMLParser
    client, cfg, found, saved, applied = controller
    cfg["displays"]["Composite-1"].update(web_url="https://youtu.be/abc123def45", youtube_mute=False, youtube_autoplay=False)
    response = client.get("/player/youtube?display=Composite-1")
    assert response.status_code == 200
    sources = []
    class Parser(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag == "iframe":
                sources.append(dict(attrs))
    Parser().feed(response.get_data(as_text=True))
    query = parse_qs(urlparse(sources[0]["src"]).query)
    assert query["origin"] == ["http://localhost"]
    assert query["mute"] == query["autoplay"] == ["0"]
    assert sources[0]["referrerpolicy"] == "strict-origin-when-cross-origin"


def test_player_route_rejects_non_youtube_and_unknown_displays(controller):
    client, cfg, found, saved, applied = controller
    cfg["displays"]["Composite-1"]["web_url"] = "https://example.invalid/private"
    assert client.get("/player/youtube?display=Composite-1").status_code == 400
    assert client.get("/player/youtube?display=unknown").status_code == 404


def test_saving_web_url_does_not_do_network_extraction(controller, monkeypatch):
    from echoview import embed_utils
    client, cfg, found, saved, applied = controller
    monkeypatch.setattr(embed_utils.requests, "get", lambda *a, **kw: pytest.fail("save network request"))
    monkeypatch.setattr(routes.subprocess, "check_call", lambda *a, **kw: None)
    response = client.post("/", data={"action": "update_displays", "Composite-1_mode": "web_page", "Composite-1_web_url": "https://youtube.com/watch?v=abc123def45"})
    assert response.status_code == 302
    assert saved[-1]["displays"]["Composite-1"]["embed_metadata"]["embed_type"] == "youtube"
