# web/extensions/update.py
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import subprocess
import os
import datetime
import requests
from web.extensions.spotify_api import SpotifyAPI

REPO_URL = "https://github.com/tpersp/EchoView"
VERSION_FILE = os.path.join(os.path.dirname(__file__), "../../version.txt")
router = APIRouter()

SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REFRESH_TOKEN = os.environ.get("SPOTIFY_REFRESH_TOKEN")

spotify_api = None
if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET and SPOTIFY_REFRESH_TOKEN:
    spotify_api = SpotifyAPI(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REFRESH_TOKEN)

def get_local_version():
    # Try git, fallback to version.txt
    try:
        ver = subprocess.check_output(["git", "describe", "--tags", "--always"], cwd=os.path.dirname(__file__), stderr=subprocess.DEVNULL).decode().strip()
        return ver
    except Exception:
        if os.path.exists(VERSION_FILE):
            with open(VERSION_FILE) as f:
                return f.read().strip()
        return "unknown"

def get_latest_github_version():
    # Use GitHub API to get latest release/tag
    try:
        api_url = f"https://api.github.com/repos/tpersp/EchoView/releases/latest"
        r = requests.get(api_url, timeout=5)
        if r.status_code == 200:
            data = r.json()
            return data.get("tag_name") or data.get("name")
    except Exception:
        pass
    return None

def get_changelog():
    # Get last 5 commits
    try:
        log = subprocess.check_output(["git", "log", "-5", "--pretty=format:%h %s (%cr)"], cwd=os.path.dirname(__file__), stderr=subprocess.DEVNULL).decode()
        return log.splitlines()
    except Exception:
        return []

@router.get("/update/version")
def version_info():
    local = get_local_version()
    latest = get_latest_github_version()
    return JSONResponse({"local": local, "latest": latest, "changelog": get_changelog(), "last_update": datetime.datetime.now().isoformat()})

@router.post("/update/check")
def check_update():
    local = get_local_version()
    latest = get_latest_github_version()
    up_to_date = (local == latest)
    return JSONResponse({"local": local, "latest": latest, "up_to_date": up_to_date})

@router.post("/update/run")
def run_update():
    # Pull latest from git and install requirements
    try:
        out = subprocess.check_output(["git", "pull"], cwd=os.path.dirname(__file__), stderr=subprocess.STDOUT).decode()
        pip_out = subprocess.check_output(["pip", "install", "-r", "requirements.txt"], cwd=os.path.dirname(__file__), stderr=subprocess.STDOUT).decode()
        msg = out + "\n" + pip_out
        status = "success"
    except Exception as e:
        msg = str(e)
        status = "error"
        if "authentication" in msg.lower() or "permission denied" in msg.lower():
            msg += "\nERROR: Make sure the repository is public and cloned using HTTPS, not SSH."
    return JSONResponse({"status": status, "output": msg})

@router.get("/spotify/info")
def spotify_info():
    if not spotify_api:
        return JSONResponse({"error": "Spotify credentials not set"}, status_code=400)
    try:
        playback = spotify_api.get_current_playback()
        if not playback or not playback.get("item"):
            return JSONResponse({"playing": False})
        item = playback["item"]
        info = {
            "playing": playback.get("is_playing", False),
            "track": item.get("name"),
            "artist": ", ".join([a["name"] for a in item.get("artists", [])]),
            "album": item.get("album", {}).get("name"),
            "album_art": item.get("album", {}).get("images", [{}])[0].get("url"),
            "progress_ms": playback.get("progress_ms"),
            "duration_ms": item.get("duration_ms"),
        }
        return JSONResponse(info)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
