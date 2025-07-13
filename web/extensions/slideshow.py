# web/extensions/slideshow.py
from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import JSONResponse
import os
import json

UPLOAD_DIR = "media"
SLIDESHOW_STATE_FILE = os.path.join(UPLOAD_DIR, "slideshow_state.json")

router = APIRouter()

def get_slideshow_state():
    if os.path.exists(SLIDESHOW_STATE_FILE):
        with open(SLIDESHOW_STATE_FILE, "r") as f:
            return json.load(f)
    return {"files": [], "current": 0, "interval": 5, "mode": "dark"}

def set_slideshow_state(state):
    with open(SLIDESHOW_STATE_FILE, "w") as f:
        json.dump(state, f)

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    file_location = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_location, "wb") as f:
        f.write(await file.read())
    # Add to slideshow state
    state = get_slideshow_state()
    if file.filename not in state["files"]:
        state["files"].append(file.filename)
        set_slideshow_state(state)
    return {"filename": file.filename}

@router.get("/slideshow")
def get_slideshow():
    state = get_slideshow_state()
    return JSONResponse(state)

@router.post("/slideshow/next")
def next_slide():
    state = get_slideshow_state()
    if state["files"]:
        state["current"] = (state["current"] + 1) % len(state["files"])
        set_slideshow_state(state)
    return JSONResponse(state)

@router.post("/slideshow/prev")
def prev_slide():
    state = get_slideshow_state()
    if state["files"]:
        state["current"] = (state["current"] - 1) % len(state["files"])
        set_slideshow_state(state)
    return JSONResponse(state)

@router.post("/slideshow/set")
def set_slide(idx: int = Form(...)):
    state = get_slideshow_state()
    if 0 <= idx < len(state["files"]):
        state["current"] = idx
        set_slideshow_state(state)
    return JSONResponse(state)

@router.post("/slideshow/interval")
def set_interval(interval: int = Form(...)):
    state = get_slideshow_state()
    state["interval"] = max(1, interval)
    set_slideshow_state(state)
    return JSONResponse(state)

@router.post("/slideshow/mode")
def set_mode(mode: str = Form(...)):
    state = get_slideshow_state()
    if mode in ["dark", "light"]:
        state["mode"] = mode
        set_slideshow_state(state)
    return JSONResponse(state)
