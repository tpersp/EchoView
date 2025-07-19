# EchoView

A modular, web-controlled media display application for Linux devices (e.g., Raspberry Pi).

## Features
- Modular plugin system for easy feature addition/removal
- Web-based control panel
- Persistent settings
- Updatable from GitHub
- SMB share integration (planned)
- Spotify integration (planned)

## Getting Started

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the server
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 3. Access the web UI
Open your browser and go to `http://<device-ip>:8000/static/`

## Adding Features
Add new modules in the `modules/` directory. Each module should have an `init_module(app, config)` function.

## Updating from GitHub
The application can update itself from the official repository. An endpoint is
exposed at `/update` which will fetch the latest commit from
`https://github.com/tpersp/EchoView.git` and reset the local copy. Any JSON
configuration files are backed up and restored so your settings remain intact.
Local changes to the code are discarded.

## Persistent Settings
Settings are stored in `config/settings.json` and survive reboots/service
restarts. The file is ignored by Git so updates will not overwrite your
configuration.

---

For questions or contributions, see the GitHub repo: https://github.com/tpersp/EchoView.git
