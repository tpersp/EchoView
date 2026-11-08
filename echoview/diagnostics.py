"""Read-only, credential-free host report: python -m echoview.diagnostics."""

import json
import os
import platform
import re
import shutil
import subprocess
from importlib import metadata
from pathlib import Path

PACKAGES = ("Flask", "Werkzeug", "psutil", "requests", "spotipy", "PySide6", "Pillow", "yt-dlp", "yt-dlp-ejs")
TOOLS = ("xrandr", "chromium", "chromium-browser", "mpv", "ffmpeg", "ffprobe", "yt-dlp", "deno", "node", "systemctl")


def run_command(args):
    """Bound every probe; callers select safe fields instead of exposing stderr."""
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=5, check=False)
        return result.returncode, result.stdout
    except (OSError, subprocess.TimeoutExpired):
        return None, ""


def package_versions():
    versions = {}
    for name in PACKAGES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def display_report():
    report = {"session_type": "unknown", "qt_platform_requested": "default", "x11_probe": "unavailable", "connectors": []}
    session = os.environ.get("XDG_SESSION_TYPE", "")
    if session in ("x11", "wayland", "tty"):
        report["session_type"] = session
    requested = os.environ.get("QT_QPA_PLATFORM", "").split(":", 1)[0]
    if requested in ("xcb", "wayland", "offscreen", "minimal", "eglfs", "linuxfb"):
        report["qt_platform_requested"] = requested
    if not shutil.which("xrandr"):
        return report
    code, output = run_command(["xrandr", "--query"])
    if code != 0:
        return report
    report["x11_probe"] = "ok"
    for line in output.splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+) (connected|disconnected)\b(.*)$", line)
        if not match:
            continue
        geometry = re.search(r"\b(\d+x\d+)([+-]\d+)([+-]\d+)", match[3])
        report["connectors"].append({
            "name": match[1], "connected": match[2] == "connected",
            "resolution": geometry[1] if geometry else None,
            "position": [int(geometry[2]), int(geometry[3])] if geometry else None,
        })
    return report


def service_report():
    services = {}
    allowed = {"active", "inactive", "failed", "activating", "deactivating", "reloading", "maintenance"}
    for name in ("lightdm.service", "echoview.service", "controller.service"):
        _, output = run_command(["systemctl", "is-active", name])
        state = output.strip()
        services[name] = state if state in allowed else "unavailable"
    return services


def collect_report():
    # Do not import application config: it reads .env. Never inspect tokens,
    # credentials, hostname, IP addresses, service environments or journal logs.
    try:
        os_name = platform.freedesktop_os_release().get("PRETTY_NAME", platform.system())
    except OSError:
        os_name = platform.system()
    try:
        model = Path("/proc/device-tree/model").read_text().rstrip("\x00\n")
    except OSError:
        model = None
    return {
        "os": os_name, "architecture": platform.machine(),
        "python": platform.python_version(), "pi_model": model,
        "packages": package_versions(),
        "tools": {name: bool(shutil.which(name)) for name in TOOLS},
        "display": display_report(), "services": service_report(),
        "notes": [
            "No credentials, token contents, hostnames, IP addresses or executable paths are collected.",
            "Qt platform is a requested setting, not a verified running backend; no GUI is launched.",
            "Service activity does not prove application readiness or successful playback.",
        ],
    }


def main():
    print(json.dumps(collect_report(), indent=2))


if __name__ == "__main__":
    main()
