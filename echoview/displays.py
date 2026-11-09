"""Shared X11 connector inventory, mode selection and display-aspect geometry."""
from copy import deepcopy
import re
import subprocess
import threading

DISPLAY_ASPECTS = {"auto": None, "4:3": 4 / 3, "16:9": 16 / 9, "16:10": 16 / 10, "1:1": 1.0}
_mode_lock = threading.Lock()


def connector_key(name):
    return re.sub(r"^HDMI-A-(\d+)$", r"HDMI-\1", name)


def match_connector(name, candidates):
    candidates = list(candidates)
    if name in candidates:
        return name
    matches = [candidate for candidate in candidates if connector_key(candidate) == connector_key(name)]
    return matches[0] if len(matches) == 1 else None


def connector_kind(name):
    return "composite" if name.lower().startswith(("composite", "tv", "vec")) else "digital"


def parse_xrandr(text):
    monitors = {}
    current = None
    edid = []

    def finish_edid():
        if current is not None and edid:
            try:
                raw = bytes.fromhex("".join(edid))
                for offset in (54, 72, 90, 108):
                    descriptor = raw[offset:offset + 18]
                    if descriptor[:5] == b"\x00\x00\x00\xfc\x00":
                        current["model"] = descriptor[5:18].decode("ascii", errors="ignore").strip()
            except ValueError:
                pass
        edid.clear()

    for line in text.splitlines():
        header = re.match(r"^([\w.-]+) (connected|disconnected|unknown connection)\b(.*)$", line)
        if header:
            finish_edid()
            name, state, rest = header.groups()
            geom = re.search(r"\b(\d+)x(\d+)([+-]\d+)([+-]\d+)", rest)
            current = monitors[name] = {
                # Composite commonly cannot sense a cable. An active CRTC is
                # sufficient evidence of an available output in that case.
                "name": name, "connected": state == "connected" or (state == "unknown connection" and geom is not None), "active": geom is not None,
                "kind": connector_kind(name), "model": None, "current_mode": None,
                "current_rate": None, "modes": [], "mode_details": [],
                "width": int(geom[1]) if geom else 0, "height": int(geom[2]) if geom else 0,
                "x": int(geom[3]) if geom else 0, "y": int(geom[4]) if geom else 0,
                "primary": bool(re.search(r"\bprimary\b", rest)),
            }
            if geom:
                current["current_mode"] = f"{geom[1]}x{geom[2]}"
            continue
        if current is None:
            continue
        if re.fullmatch(r"\s*[0-9A-Fa-f]{32}\s*", line):
            edid.append(line.strip())
            continue
        if edid:
            finish_edid()
        if "Monitor name:" in line:
            current["model"] = line.split("Monitor name:", 1)[1].strip() or None
        mode = re.match(r"^\s+(\d+x\d+[\w.+-]*)\s+((?:\d+(?:\.\d+)?[i*+]*\s*)+)$", line)
        if not mode:
            continue
        name, rates_text = mode.groups()
        dimensions = re.match(r"(\d+)x(\d+)", name)
        rates = []
        preferred = False
        for token in rates_text.split():
            rate = token.rstrip("i*+")
            if rate not in rates:
                rates.append(rate)
            preferred = preferred or "+" in token
            if "*" in token:
                current["current_mode"], current["current_rate"] = name, rate
        current["modes"].append(name)
        current["mode_details"].append({"name": name, "width": int(dimensions[1]), "height": int(dimensions[2]), "rates": rates, "preferred": preferred})
    finish_edid()
    return monitors


def discover_monitors():
    try:
        result = subprocess.run(["xrandr", "--query", "--props"], capture_output=True, text=True, timeout=5, check=True)
        return parse_xrandr(result.stdout)
    except (OSError, subprocess.SubprocessError):
        return {}


def mode_choices(monitor):
    choices = []
    for mode in monitor.get("mode_details", []):
        for rate in mode["rates"]:
            value = mode["name"] + "@" + rate
            choices.append({"value": value, "label": f'{mode["name"]} @ {rate} Hz'})
    return choices


def default_display(name):
    return {"mode": "random_image", "fallback_mode": "random_image", "image_interval": 60,
            "image_category": "", "specific_image": "", "shuffle_mode": False,
            "mixed_folders": [], "rotate": 0, "aspect_filter": "any", "connector": name,
            "output_mode": "auto", "display_aspect": "auto",
            "safe_area": {"left": 0, "right": 0, "top": 0, "bottom": 0}, "resource_profile": "standard"}


def reconcile_displays(cfg, inventory):
    """Preserve offline settings and migrate only unambiguous legacy identities."""
    before = deepcopy(cfg)
    saved = cfg.setdefault("displays", {})
    connected = [name for name, mon in inventory.items() if mon.get("connected")]
    if len(saved) == 1 and len(connected) == 1:
        legacy = next(iter(saved))
        if legacy.lower() in ("display0", "default") and legacy != connected[0]:
            saved[connected[0]] = saved.pop(legacy)
    for name in connected:
        if name not in saved:
            alias = match_connector(name, saved)
            if alias and alias != name:
                saved[name] = saved.pop(alias)
            else:
                saved[name] = default_display(name)
        display = saved[name]
        for key, value in default_display(name).items():
            display.setdefault(key, value)
        display["connector"] = name
        monitor = inventory[name]
        display["screen_name"] = f'{name}: {monitor.get("current_mode") or "inactive"}'
        if monitor.get("model"):
            display["monitor_model"] = monitor["model"]
    return cfg != before


def apply_output_mode(name, selection, discover=None, runner=None):
    """Apply only advertised modes, verify actual state, roll back failed changes."""
    discover = discover or discover_monitors
    runner = runner or subprocess.run
    with _mode_lock:
        inventory = discover()
        if name not in inventory or not inventory[name]["connected"]:
            raise ValueError("Output is disconnected or X11 display discovery is unavailable.")
        original = inventory[name]
        options = {item["value"] for item in mode_choices(original)}
        if selection != "auto" and selection not in options:
            raise ValueError("Select an advertised resolution and refresh rate; custom modelines are not supported.")
        if selection == "auto":
            args = ["--auto"]
        else:
            mode, rate = selection.rsplit("@", 1)
            if original["active"] and original["current_mode"] == mode and original["current_rate"] == rate:
                return original
            args = ["--mode", mode, "--rate", rate]
        def run(arguments):
            runner(["xrandr", "--output", name] + arguments, capture_output=True, text=True, check=True, timeout=5)
        try:
            run(args)
            actual = discover().get(name)
            if not actual or not actual["active"]:
                raise ValueError("Output did not become active.")
            if selection != "auto" and (actual["current_mode"] != mode or actual["current_rate"] != rate):
                raise ValueError("Output did not switch to the requested mode.")
            return actual
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            rollback = ["--mode", original["current_mode"]] if original["active"] else ["--off"]
            if original["active"] and original["current_rate"]:
                rollback += ["--rate", original["current_rate"]]
            try:
                run(rollback)
            except (OSError, subprocess.SubprocessError):
                raise RuntimeError("Mode change and rollback failed; use the web controller or local X11 tools to recover.") from None
            raise ValueError("Mode change failed; the previous mode was requested again. Saved settings are unchanged.") from exc


def display_pixel_aspect(setting, width, height, connector=""):
    if width <= 0 or height <= 0:
        return 1.0
    physical = DISPLAY_ASPECTS.get(setting)
    if setting == "auto" and connector_kind(connector) == "composite":
        physical = 4 / 3
    return physical / (width / height) if physical else 1.0


def fit_dimensions(iw, ih, width, height, pixel_aspect=1.0):
    if min(iw, ih, width, height) <= 0:
        return width, height
    ratio = iw / ih / pixel_aspect
    if ratio > width / height:
        return width, max(1, round(width / ratio))
    return max(1, round(height * ratio)), height


def screen_assignments(cfg, screens):
    """Match by identity only; never place a missing output on another screen."""
    names = [screen.name() for screen in screens if screen.name()]
    by_name = {screen.name(): screen for screen in screens if screen.name() and names.count(screen.name()) == 1}
    targets = {}
    # Reserve exact names first, so an alias never steals another saved output.
    for name, display in cfg.get("displays", {}).items():
        connector = display.get("connector") or name
        if connector in by_name:
            targets[name] = connector
    used = set(targets.values())
    for name, display in cfg.get("displays", {}).items():
        if name not in targets:
            match = match_connector(display.get("connector") or name, by_name)
            if match and match not in used:
                targets[name] = match
                used.add(match)
    assigned = []
    used.clear()
    for name in cfg.get("displays", {}):
        match = targets.get(name)
        if match and match not in used:
            assigned.append((name, by_name[match]))
            used.add(match)
    return assigned
