"""Optional streaming capabilities and process arguments; no Qt or network calls."""
import argparse
from importlib import metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

STARTED_MARKER = "ECHOVIEW_PLAYBACK_STARTED"


def tool_path(name):
    local = Path(sys.executable).parent / name
    return str(local) if local.is_file() and os.access(local, os.X_OK) else shutil.which(name)


def playback_environment():
    env = os.environ.copy()
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    return env


def capabilities(probe_runtime=True):
    packages = {}
    for name in ("yt-dlp", "yt-dlp-ejs", "deno"):
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = None
    tools = {name: bool(tool_path(name)) for name in ("mpv", "ffmpeg", "yt-dlp", "deno")}
    version = None
    if not probe_runtime and packages["deno"]:
        match = re.match(r"(\d+)\.(\d+)\.(\d+)", packages["deno"])
        version = tuple(map(int, match.groups())) if match else None
    if tools["deno"] and probe_runtime:
        try:
            result = subprocess.run([tool_path("deno"), "--version"], capture_output=True, text=True, timeout=5, check=True)
            match = re.search(r"^deno (\d+)\.(\d+)\.(\d+)", result.stdout)
            if match:
                version = tuple(map(int, match.groups()))
        except (OSError, subprocess.SubprocessError):
            pass
    missing = [name for name, present in packages.items() if not present]
    missing += [name + " executable" for name in ("yt-dlp", "deno", "mpv", "ffmpeg") if not tools[name]]
    if tools["deno"] and (not version or version < (2, 9, 8)):
        missing.append("Deno 2.9.8+ runtime")
    return {"ready": not missing, "runtime_probed": probe_runtime, "packages": packages, "tools": tools,
            "deno_version": ".".join(map(str, version)) if version else None,
            "missing": missing}


def stream_height(display, output_height=None):
    quality = display.get("youtube_quality", "default")
    heights = {"small": 240, "medium": 360, "large": 480, "hd720": 720, "hd1080": 1080, "highres": 2160}
    height = heights.get(quality, 1080)
    if output_height and quality == "default":
        height = min(height, max(144, int(output_height)))
    return min(height, 480) if display.get("resource_profile") == "pi3" else height


def format_selector(height):
    cap = f"[height<={height}]"
    return (f"bestvideo{cap}[vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
            f"best{cap}[vcodec^=avc1]/bestvideo{cap}+bestaudio/best{cap}")


def stream_flags(display, youtube=False, output_height=None, start_seconds=None):
    flags = ["--network-timeout=10", "--ytdl-raw-options=socket-timeout=10,extractor-retries=1,retries=1,fragment-retries=1",
             "--script=" + str(Path(__file__).with_name("mpv_observer.lua")),
             "--msg-level=all=error,mpv_observer=info"]
    if youtube:
        flags += [f"--ytdl-format={format_selector(stream_height(display, output_height))}",
                  "--mute=" + ("yes" if display.get("youtube_mute", True) else "no"),
                  "--pause=" + ("no" if display.get("youtube_autoplay", True) else "yes"),
                  "--sub-visibility=" + ("yes" if display.get("youtube_captions", False) else "no")]
        if start_seconds:
            flags.append(f"--start={max(0, int(start_seconds))}")
    return flags


def parse_player_event(line):
    match = re.fullmatch(r"\[mpv_observer\] ECHOVIEW_PLAYBACK_STARTED\|([^\s]+)\s*", line.strip())
    if not match:
        return None
    try:
        duration = float(match[1])
        live = duration <= 0
    except ValueError:
        live = match[1] in ("N/A", "nan")
    return "playing_live" if live else "playing"


class RetryPolicy:
    """Two retries per interruption; reset only after a minute of stable playback."""
    def __init__(self, clock=time.monotonic):
        self.failures = 0
        self.clock = clock
        self.started_at = None

    def mark_started(self):
        if self.started_at is None:
            self.started_at = self.clock()

    def next_delay(self):
        if self.started_at is not None and self.clock() - self.started_at >= 60:
            self.failures = 0
        self.started_at = None
        if self.failures >= 2:
            return None
        delay = (2000, 5000)[self.failures]
        self.failures += 1
        return delay


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if the packaged streaming stack is incomplete")
    args = parser.parse_args(argv)
    report = capabilities()
    print(json.dumps(report, indent=2))
    return 1 if args.check and not report["ready"] else 0


if __name__ == "__main__":
    sys.exit(main())
