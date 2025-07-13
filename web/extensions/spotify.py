from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from config import load_config, save_config
import spotipy
from spotipy.oauth2 import SpotifyOAuth

router = APIRouter()

@router.get("/spotify/status")
async def spotify_status():
    cfg = load_config()
    sp_cfg = cfg.get("spotify", {})
    cid = sp_cfg.get("client_id", "")
    csec = sp_cfg.get("client_secret", "")
    ruri = sp_cfg.get("redirect_uri", "")
    scope = sp_cfg.get("scope", "user-read-currently-playing user-read-playback-state")
    if not (cid and csec and ruri):
        return JSONResponse(content={"status": "incomplete"})
    try:
        auth = SpotifyOAuth(client_id=cid, client_secret=csec, redirect_uri=ruri, scope=scope, cache_path=".spotify_cache")
        token_info = auth.get_cached_token()
        if not token_info:
            return JSONResponse(content={"status": "unauthorized"})
        sp = spotipy.Spotify(auth=token_info["access_token"])
        current = sp.current_playback()
        if not current or not current.get("item"):
            return JSONResponse(content={"status": "no_track"})
        item = current["item"]
        return JSONResponse(content={
            "status": "playing",
            "track": item.get("name", ""),
            "artist": ", ".join([a.get("name", "") for a in item.get("artists", [])]),
            "album": item.get("album", {}).get("name", "")
        })
    except Exception as e:
        return JSONResponse(content={"status": "error", "error": str(e)})

@router.post("/spotify/config")
async def update_spotify_config(request: Request):
    data = await request.json()
    cfg = load_config()
    cfg["spotify"] = data
    save_config(cfg)
    return JSONResponse(content={"message": "Spotify config updated."})

# This file is intentionally left empty. All extension logic is now in web/extensions/*.py.
