import json
import subprocess

from echoview import diagnostics


def test_connector_report_handles_no_edid_and_negative_coordinates(monkeypatch):
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: "/usr/bin/xrandr")
    monkeypatch.setattr(diagnostics, "run_command", lambda args: (0, (
        "HDMI-1 connected primary 1920x1080+0+0 (normal)\n"
        "Composite-1 connected 720x576-720+0 (normal)\n"
        "HDMI-2 disconnected (normal)\n"
        "  EDID: private data\n")))
    report = diagnostics.display_report()
    assert report["connectors"][1] == {
        "name": "Composite-1", "connected": True,
        "resolution": "720x576", "position": [-720, 0],
    }
    assert report["connectors"][2]["resolution"] is None
    assert "private data" not in json.dumps(report)


def test_probes_timeout_without_exposing_errors(monkeypatch):
    def timeout(*args, **kwargs):
        assert kwargs["timeout"] == 5
        raise subprocess.TimeoutExpired(args[0], 5, stderr="secret")
    monkeypatch.setattr(diagnostics.subprocess, "run", timeout)
    assert diagnostics.run_command(["systemctl", "is-active", "echoview.service"]) == (None, "")
    assert set(diagnostics.service_report().values()) == {"unavailable"}


def test_environment_and_probe_errors_are_not_dumped(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "sensitive-marker")
    monkeypatch.setenv("QT_QPA_PLATFORM", "sensitive-marker")
    monkeypatch.setenv("XDG_SESSION_TYPE", "sensitive-marker")
    monkeypatch.setattr(diagnostics, "run_command", lambda args: (1, "sensitive-marker"))
    encoded = json.dumps(diagnostics.collect_report())
    assert "sensitive-marker" not in encoded
    assert "unavailable" in encoded
