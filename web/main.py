from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
import os
import json
import platform
import psutil
from fastapi import Form
from fastapi.responses import RedirectResponse
import glob
import random

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "media"
SETTINGS_DIR = "config"
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "screen_settings.json")
os.makedirs(SETTINGS_DIR, exist_ok=True)

SLIDESHOW_STATE_FILE = os.path.join(UPLOAD_DIR, "slideshow_state.json")
MODES = ["specific_file", "random_file", "spotify", "mixed"]

def get_slideshow_state():
    if os.path.exists(SLIDESHOW_STATE_FILE):
        with open(SLIDESHOW_STATE_FILE, "r") as f:
            return json.load(f)
    return {"files": [], "current": 0, "interval": 5, "mode": "dark"}

def set_slideshow_state(state):
    with open(SLIDESHOW_STATE_FILE, "w") as f:
        json.dump(state, f)

def get_screen_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    # If missing, create with defaults
    default = {
        "mode": "random_file",
        "specific_file": None,
        "random_folder": "ALL",
        "mixed_files": [],
        "mixed_folders": [],
        "spotify": {},
    }
    with open(SETTINGS_FILE, "w") as f:
        json.dump(default, f, indent=2)
    return default

def set_screen_settings(settings):
    # Save all settings, including any new keys
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)

@app.post("/upload")
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

@app.get("/slideshow")
def get_slideshow():
    state = get_slideshow_state()
    return JSONResponse(state)

@app.post("/slideshow/next")
def next_slide():
    state = get_slideshow_state()
    if state["files"]:
        state["current"] = (state["current"] + 1) % len(state["files"])
        set_slideshow_state(state)
    return JSONResponse(state)

@app.post("/slideshow/prev")
def prev_slide():
    state = get_slideshow_state()
    if state["files"]:
        state["current"] = (state["current"] - 1) % len(state["files"])
        set_slideshow_state(state)
    return JSONResponse(state)

@app.post("/slideshow/set")
def set_slide(idx: int = Form(...)):
    state = get_slideshow_state()
    if 0 <= idx < len(state["files"]):
        state["current"] = idx
        set_slideshow_state(state)
    return JSONResponse(state)

@app.post("/slideshow/interval")
def set_interval(interval: int = Form(...)):
    state = get_slideshow_state()
    state["interval"] = max(1, interval)
    set_slideshow_state(state)
    return JSONResponse(state)

@app.post("/slideshow/mode")
def set_mode(mode: str = Form(...)):
    state = get_slideshow_state()
    if mode in ["dark", "light"]:
        state["mode"] = mode
        set_slideshow_state(state)
    return JSONResponse(state)

@app.post("/screen-settings")
def update_screen_settings(
    mode: str = Form(...),
    specific_file: str = Form(None),
    random_folder: str = Form(None),
    mixed_files: str = Form(None),  # comma-separated
    mixed_folders: str = Form(None),  # comma-separated
):
    settings = get_screen_settings()
    settings["mode"] = mode
    settings["specific_file"] = specific_file
    settings["random_folder"] = random_folder
    settings["mixed_files"] = mixed_files.split(",") if mixed_files else []
    settings["mixed_folders"] = mixed_folders.split(",") if mixed_folders else []
    set_screen_settings(settings)
    return {"ok": True, "settings": settings}

@app.post("/screen-settings/save")
def save_screen_settings(
    mode: str = Form(...),
    specific_file: str = Form(None),
    random_folder: str = Form(None),
    mixed_files: str = Form(None),
    mixed_folders: str = Form(None),
    spotify_font_size: int = Form(56),
    spotify_info_position: str = Form("Top Left"),
    progress_bar_position: str = Form("Bottom Center"),
    progress_bar_theme: str = Form("Dark"),
    rotate: int = Form(0),
    auto_negative_font: str = Form("on")
):
    settings = get_screen_settings()
    settings["mode"] = mode
    settings["specific_file"] = specific_file
    settings["random_folder"] = random_folder
    settings["mixed_files"] = mixed_files.split(",") if mixed_files else []
    settings["mixed_folders"] = mixed_folders.split(",") if mixed_folders else []
    settings["spotify_font_size"] = spotify_font_size
    settings["spotify_info_position"] = spotify_info_position
    settings["progress_bar_position"] = progress_bar_position
    settings["progress_bar_theme"] = progress_bar_theme
    settings["rotate"] = rotate
    settings["auto_negative_font"] = (auto_negative_font == "on")
    set_screen_settings(settings)
    return {"ok": True, "settings": settings}

@app.get("/screen-settings")
def get_screen_settings_api():
    return get_screen_settings()

@app.get("/slideshow/current")
def get_current_slide():
    settings = get_screen_settings()
    mode = settings.get("mode", "random_file")
    if mode == "specific_file" and settings.get("specific_file"):
        file_path = os.path.join(UPLOAD_DIR, settings["specific_file"])
        if os.path.isfile(file_path):
            return {"filename": settings["specific_file"]}
    elif mode == "random_file":
        folder = settings.get("random_folder")
        if folder in [None, '', 'ALL']:
            # All folders: gather all files in all folders and root
            files = [f for f in os.listdir(UPLOAD_DIR) if os.path.isfile(os.path.join(UPLOAD_DIR, f))]
            for sub in os.listdir(UPLOAD_DIR):
                sub_path = os.path.join(UPLOAD_DIR, sub)
                if os.path.isdir(sub_path):
                    files.extend([os.path.join(sub, f) for f in os.listdir(sub_path) if os.path.isfile(os.path.join(sub_path, f))])
            if files:
                return {"filename": random.choice(files)}
        else:
            folder_path = os.path.join(UPLOAD_DIR, folder)
            if os.path.isdir(folder_path):
                files = [os.path.join(folder, f) for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
                if files:
                    return {"filename": random.choice(files)}
    elif mode == "mixed":
        files = [f for f in settings.get("mixed_files", []) if os.path.isfile(os.path.join(UPLOAD_DIR, f))]
        for folder in settings.get("mixed_folders", []):
            folder_path = os.path.join(UPLOAD_DIR, folder)
            if os.path.isdir(folder_path):
                folder_files = [os.path.join(folder, f) for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
                files.extend(folder_files)
        if files:
            rel_file = random.choice(files)
            return {"filename": rel_file}
    elif mode == "spotify":
        return {"filename": None, "spotify": True}
    state = get_slideshow_state()
    if state["files"]:
        return {"filename": state["files"][state["current"]]}
    return {"filename": None}

def get_device_info():
    info = {
        "hostname": platform.node(),
        "os": platform.system() + " " + platform.release(),
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "mem_total": psutil.virtual_memory().total,
        "mem_used": psutil.virtual_memory().used,
        "mem_percent": psutil.virtual_memory().percent,
        "temp": None
    }
    # Try to get temperature (Linux only, fallback to None)
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for name, entries in temps.items():
                for entry in entries:
                    if hasattr(entry, 'current'):
                        info["temp"] = entry.current
                        break
                if info["temp"] is not None:
                    break
    except Exception:
        pass
    return info

@app.get("/device-info")
def device_info():
    return get_device_info()

# Mount static files
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "")), name="static")

# Jinja2 templates
templates = Jinja2Templates(directory=os.path.dirname(__file__))

@app.get("/")
def root(request: Request):
    return templates.TemplateResponse("screens.html", {"request": request, "title": "EchoViewer Controller", "active": "screens"})

@app.get("/upload")
def upload_page(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request, "title": "Upload Media - EchoViewer", "active": "upload"})

@app.get("/settings")
def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request, "title": "Settings - EchoViewer", "active": "settings"})

@app.get("/screen-settings-ui")
def screen_settings_ui(request: Request):
    files = [f for f in os.listdir(UPLOAD_DIR) if os.path.isfile(os.path.join(UPLOAD_DIR, f))]
    folders = [f for f in os.listdir(UPLOAD_DIR) if os.path.isdir(os.path.join(UPLOAD_DIR, f))]
    settings = get_screen_settings()
    files_options = ''.join([f"<option value='{f}' {'selected' if settings.get('specific_file')==f else ''}>{f}</option>" for f in files])
    folders_options = "<option value='ALL' {}>All Folders</option>".format('selected' if settings.get('random_folder') in [None, '', 'ALL'] else '')
    folders_options += ''.join([f"<option value='{f}' {'selected' if settings.get('random_folder')==f else ''}>{f}</option>" for f in folders])
    mixed_files_options = ''.join([f"<option value='{f}' {'selected' if f in settings.get('mixed_files', []) else ''}>{f}</option>" for f in files])
    mixed_folders_options = ''.join([f"<option value='{f}' {'selected' if f in settings.get('mixed_folders', []) else ''}>{f}</option>" for f in folders])
    mode = settings.get('mode', 'random_file')
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang='en'>
    <head>
    <meta charset='UTF-8'>
    <meta name='viewport' content='width=device-width, initial-scale=1.0'>
    <title>Screen Settings - EchoViewer</title>
    <link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap' rel='stylesheet'>
    <style>
    body {{ background: #181a1b; color: #f3f3f3; font-family: 'Inter', sans-serif; }}
    .container {{ max-width: 480px; margin: 2em auto; background: #23272e; border-radius: 14px; box-shadow: 0 4px 24px #0006; padding: 2em; }}
    label {{ display: block; margin: 1em 0 0.3em 0; }}
    select, input[type=text], input[type=number] {{ width: 100%; padding: 0.5em; border-radius: 7px; border: 1px solid #333a; background: #181a1b; color: #fff; }}
    button {{ background: #2d8cf0; color: #fff; border: none; border-radius: 7px; padding: 0.7em 1.5em; font-weight: 600; margin-top: 1.5em; cursor: pointer; }}
    .row {{ margin-bottom: 1em; }}
    .hidden {{ display: none; }}
    </style>
    </head>
    <body>
    <div class='container'>
      <h2>Screen Slideshow Mode Settings</h2>
      <form method='post' action='/screen-settings-ui'>
        <label>Mode:
          <select name='mode' id='mode' onchange='updateModeFields()'>
            <option value='specific_file' {'selected' if mode=='specific_file' else ''}>Specific File</option>
            <option value='random_file' {'selected' if mode=='random_file' else ''}>Random Image (All Folders)</option>
            <option value='mixed' {'selected' if mode=='mixed' else ''}>Mixed (Files/Folders)</option>
            <option value='spotify' {'selected' if mode=='spotify' else ''}>Spotify</option>
          </select>
        </label>
        <div id='mode-fields'>
        </div>
        <div id='spotify-fields' class='hidden'>
          <label>Fallback Mode:
            <select name='fallback_mode'>
              <option value='random_file'>Random Image/GIF</option>
              <option value='blank'>Blank</option>
            </select>
          </label>
          <label>Spotify Font Size:<input type='number' name='spotify_font_size' min='10' max='200' value='56'></label>
          <label>Spotify Info Position:
            <select name='spotify_info_position'>
              <option>Top Left</option>
              <option>Top Right</option>
              <option>Bottom Left</option>
              <option>Bottom Right</option>
              <option>Center</option>
            </select>
          </label>
          <label>Progress Bar Position:
            <select name='progress_bar_position'>
              <option>Bottom Center</option>
              <option>Top Center</option>
              <option>Bottom Left</option>
              <option>Bottom Right</option>
            </select>
          </label>
          <label>Progress Bar Theme:
            <select name='progress_bar_theme'>
              <option>Dark</option>
              <option>Light</option>
              <option>Accent</option>
            </select>
          </label>
          <label>Rotate (degrees):<input type='number' name='rotate' min='0' max='359' value='0'></label>
          <label><input type='checkbox' name='auto_negative_font' checked> Auto Negative Font</label>
        </div>
        <button type='submit'>Save Settings</button>
      </form>
    </div>
    <script>
    function updateModeFields() {{
      let mode = document.getElementById('mode').value;
      let html = '';
      document.getElementById('spotify-fields').classList.add('hidden');
      if (mode === 'specific_file') {{
        html += `<label>File:<select name='specific_file'>{files_options}</select></label>`;
      }} else if (mode === 'random_file') {{
        html += `<label>Folder:<select name='random_folder'>{folders_options}</select></label>`;
      }} else if (mode === 'mixed') {{
        html += `<label>Files:<select name='mixed_files' multiple size='5'>{mixed_files_options}</select></label>`;
        html += `<label>Folders:<select name='mixed_folders' multiple size='3'>{mixed_folders_options}</select></label>`;
      }} else if (mode === 'spotify') {{
        document.getElementById('spotify-fields').classList.remove('hidden');
      }}
      document.getElementById('mode-fields').innerHTML = html;
    }}
    document.addEventListener('DOMContentLoaded', updateModeFields);
    document.getElementById('mode').addEventListener('change', updateModeFields);
    </script>
    </body>
    </html>
    """)

@app.post("/screen-settings-ui")
def screen_settings_ui_post(request: Request):
    import asyncio
    async def handle():
        form = await request.form()
        mode = form.get('mode')
        specific_file = form.get('specific_file')
        random_folder = form.get('random_folder')
        mixed_files = form.getlist('mixed_files') if 'mixed_files' in form else []
        mixed_folders = form.getlist('mixed_folders') if 'mixed_folders' in form else []
        fallback_mode = form.get('fallback_mode')
        spotify_font_size = form.get('spotify_font_size')
        spotify_info_position = form.get('spotify_info_position')
        progress_bar_position = form.get('progress_bar_position')
        progress_bar_theme = form.get('progress_bar_theme')
        rotate = form.get('rotate')
        auto_negative_font = form.get('auto_negative_font')
        settings = get_screen_settings()
        settings['mode'] = mode
        settings['specific_file'] = specific_file
        settings['random_folder'] = random_folder
        settings['mixed_files'] = mixed_files
        settings['mixed_folders'] = mixed_folders
        if mode == 'spotify':
            settings['fallback_mode'] = fallback_mode
            settings['spotify_font_size'] = int(spotify_font_size) if spotify_font_size else 56
            settings['spotify_info_position'] = spotify_info_position or 'Top Left'
            settings['progress_bar_position'] = progress_bar_position or 'Bottom Center'
            settings['progress_bar_theme'] = progress_bar_theme or 'Dark'
            settings['rotate'] = int(rotate) if rotate else 0
            settings['auto_negative_font'] = bool(auto_negative_font)
        else:
            # Remove spotify-specific settings if not in spotify mode
            for k in ['fallback_mode','spotify_font_size','spotify_info_position','progress_bar_position','progress_bar_theme','rotate','auto_negative_font']:
                settings.pop(k, None)
        set_screen_settings(settings)
        return RedirectResponse('/screen-settings-ui', status_code=303)
    return asyncio.run(handle())

@app.get("/update")
def update_page(request: Request):
    return templates.TemplateResponse("update.html", {"request": request, "title": "Update - EchoViewer", "active": "update"})

# Modular extension loading
from web.extensions import slideshow, settings, update

app.include_router(slideshow.router)
app.include_router(settings.router)
app.include_router(update.router)

app.mount("/media", StaticFiles(directory=UPLOAD_DIR), name="media")
