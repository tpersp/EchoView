# web/extensions/settings.py
from fastapi import APIRouter, Form
import os
import json
from web.extensions.spotify_api import SpotifyAPI

UPLOAD_DIR = "media"
SETTINGS_FILE = os.path.join(UPLOAD_DIR, "screen_settings.json")

router = APIRouter()

SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REFRESH_TOKEN = os.environ.get("SPOTIFY_REFRESH_TOKEN")

spotify_api = None
if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET and SPOTIFY_REFRESH_TOKEN:
    spotify_api = SpotifyAPI(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REFRESH_TOKEN)

def get_screen_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    return {
        "mode": "random_file",
        "specific_file": None,
        "random_folder": "ALL",
        "mixed_files": [],
        "mixed_folders": [],
        "spotify": {},
    }

def set_screen_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)

@router.post("/screen-settings")
def update_screen_settings(
    mode: str = Form(...),
    specific_file: str = Form(None),
    random_folder: str = Form(None),
    mixed_files: str = Form(None),
    mixed_folders: str = Form(None),
):
    settings = get_screen_settings()
    settings["mode"] = mode
    settings["specific_file"] = specific_file
    settings["random_folder"] = random_folder
    settings["mixed_files"] = mixed_files.split(",") if mixed_files else []
    settings["mixed_folders"] = mixed_folders.split(",") if mixed_folders else []
    set_screen_settings(settings)
    return {"ok": True, "settings": settings}

@router.get("/screen-settings")
def get_screen_settings_api():
    return get_screen_settings()

@router.get("/spotify/info")
def spotify_info():
    if not spotify_api:
        return {"error": "Spotify credentials not set"}
    try:
        playback = spotify_api.get_current_playback()
        if not playback or not playback.get("item"):
            return {"playing": False}
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
        return info
    except Exception as e:
        return {"error": str(e)}
