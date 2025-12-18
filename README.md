# EchoView

EchoView is a modern, easy-to-configure slideshow + overlay viewer written in **Python/PySide6** along with a companion **Flask**-based web interface. It seamlessly supports multiple monitors on a Raspberry Pi and can optionally display a live overlay (e.g. clock) on top of your images or GIFs.

## Key Features

- **Multiple Monitors**: Launches a PySide6 window per detected monitor, each with its own display mode (Random, Mixed, Spotify, Web Page, etc.).
- **Web Controller**: A Flask web interface (on port **8080**) lets you manage sub-devices, change the slideshow folder, set intervals, shuffle, or pick a single image.
- **Aspect Filtering**: Per‑display option to only show square (1:1), landscape (16:9), or portrait (9:16) media.
- **Systemd Integration**: The `setup.sh` script creates two systemd services:
  - `echoview.service` - runs the PySide6 slideshow windows
  - `controller.service` - runs the Flask app
- **Overlay**: Optionally display time or custom text overlay in a semi-transparent box.
- **Spotify Integration**: Show currently playing track’s album art on a display.
- **Web Page Mode**: Display any live web page by entering its URL.

## Installation

These instructions assume you have a clean Raspberry Pi OS image (Lite or Desktop) with **X11**.

1. **Clone the Repository**:

```bash
sudo apt update
sudo apt install -y git
cd ~
git clone https://github.com/tpersp/EchoView.git
cd EchoView
```

2. **Run Setup**:

```bash
chmod +x setup.sh
sudo ./setup.sh
```

During the setup:

- **Apt packages** are installed (LightDM, Xorg, Python3, etc.)
- **WebEngine libs** like `libwebp7`, `libtiff6`, `libxslt1.1`, and `libminizip1t64` are installed,
  with compatibility symlinks created for `libwebp.so.6` and `libtiff.so.5` if needed.
- **pip packages** from `requirements.txt` are installed inside an isolated virtualenv
- **Screen blanking** is disabled
- You’ll be prompted for the user that will auto-login into X, the path for `VIEWER_HOME` and `IMAGE_DIR`.
- **Optionally** mount a CIFS share at `IMAGE_DIR`, or skip to use a local uploads folder.
- Systemd services are created and enabled.
- The system is **rebooted** (unless you run `--auto-update`).

3. **Post-Reboot**:
   - LightDM auto-logs into the specified user’s X session.
   - `echoview.service` runs, launching a PySide6 slideshow window on each detected screen.
   - `controller.service` hosts the web UI on **port 8080**.

## Usage

Once the Pi is up and running:

### Web Interface

Browse to `http://<PI-IP>:8080` to access the interface. You’ll see:

- **Main Screen** (`index.html`)
  - Displays system stats (CPU, memory, temp)
  - Lets you configure each local display’s mode (Random, Specific, Mixed, or Spotify)
  - For Specific mode, choose exactly one image. For Mixed, drag-drop multiple folders.
  - **Manage** how often images rotate, shuffle, etc.

- **Settings** Page
  - Set the web theme (Dark, Light, or Custom) and optionally upload a background image

- **Overlay Settings**
  - Enable or disable the overlay box
  - Position, size, and color of the overlay
  - Font sizes, clock toggles, etc.

### YouTube Live Streams

- Make sure the YouTube channel you embed has the **Live Streaming** and **Embed Live Streams** permissions enabled; YouTube currently requires account verification and at least 1,000 subscribers before granting these features.
- Only public or unlisted streams can be embedded. Private broadcasts will refuse to load inside EchoView (or any external player).
- EchoView first tries to extract the channel’s live HLS manifest using `yt_dlp`; when successful it plays the `.m3u8` feed directly through Qt Multimedia.
- If no manifest is available, EchoView launches `mpv` with the original YouTube URL. Make sure both `yt_dlp` and `mpv` are installed on the host so this fallback works seamlessly.

### Spotify Integration

In `Configure Spotify`, provide your **Client ID**, **Client Secret**, and **Redirect URI** from the Spotify Developer Dashboard. Then click **Authorize Spotify** to store the OAuth token. You can set one or more displays to `spotify` mode.

The OAuth token is cached at the location specified by the `SPOTIFY_CACHE_PATH`

environment variable. If you do not set this variable, EchoView stores the
token in `VIEWER_HOME/.spotify_cache` and will create that directory if needed.
You can override the path by adding `SPOTIFY_CACHE_PATH` to your `.env` file.

### Media Upload

Use the **Upload Media** page to add images/GIFs. You can place them in existing subfolders or create a new one. If you have a CIFS share, it will appear under your `IMAGE_DIR`.
The file manager also lets you download images and move them between folders. Folders are always shown alphabetically for easier navigation.


## Directory Structure

Below is a simplified layout:

```
EchoView/
├── echoview/
│   ├── config.py          # Paths, version info
│   ├── utils.py           # Shared functions (config I/O, logging, etc.)
│   ├── viewer.py          # PySide6 main script creating slideshow windows
│   └── web/
│       ├── app.py         # Flask entry point
│       ├── routes.py      # Flask routes
│       └── __init__.py
├── setup.sh               # Automated setup script
├── requirements.txt       # Required pip packages
├── static/
│   ├── style.css
│   ├── favicon.png
│   └── icon.png
├── templates/
│   ├── index.html
│   ├── settings.html
│   ├── overlay.html
│   ├── configure_spotify.html
│   ├── upload_media.html
│   ...
├── tests/                 # Basic unit tests
└── README.md              # This README
```

## Systemd Services

Two services are created:

- **echoview.service**
  - Runs `python3 -m echoview.viewer` at boot so the slideshows start automatically on every connected screen.
- **controller.service**
  - Runs `python3 -m echoview.web.app`, the Flask server on port 8080.

You can check their status or logs:

```bash
sudo systemctl status echoview.service
sudo systemctl status controller.service

sudo journalctl -u echoview.service
sudo journalctl -u controller.service
```

## Updating

To update EchoView while preserving your existing configuration, run:

```bash
sudo ./setup.sh --auto-update
```

This mode reinstalls dependencies and refreshes the systemd service files.
If a `.env` file already exists in your `VIEWER_HOME`, its `VIEWER_HOME` and
`IMAGE_DIR` values are reused and not overwritten.

## Troubleshooting

- **No images?** Ensure images exist in the `IMAGE_DIR` (or subfolders). By default, check `/mnt/EchoViews` or wherever you mounted.
- **Wrong screen**? Confirm you have multiple monitors recognized by X. EchoView uses PySide6’s screen geometry, so make sure your environment is not on Wayland.
- **Spotify issues**? Check the file specified by `SPOTIFY_CACHE_PATH` for the saved token. Re-authorize if needed.
- **Overlay not transparent?** You need a compositor (like **picom**) running for real transparency.
- **Web viewer blank?** Ensure the system libraries `libxslt1.1` and `libminizip1t64`
  are installed and that symlinks exist for `libwebp.so.6` and `libtiff.so.5`.
- **Check logs**: Look at `echoview.log` (in your `VIEWER_HOME`) or `journalctl -u echoview.service`.

### View the attached monitors remotely (x11vnc)

If you need to see exactly what the Pi is displaying on its connected screens, you can expose the running X session over VNC with `x11vnc`.

1) Install:

```bash
sudo apt update
sudo apt install -y x11vnc
```

2) Manual test (run while the monitors are on and LightDM is running):

```bash
x11vnc -display :0 -auth guess -forever -shared
```

Then connect from a VNC client (e.g., MobaXterm):
- Protocol: VNC
- Host: `pi-ip`
- Port: `5900`

You should see the live output from the attached monitors. If this works, stop here unless you want it to start automatically.

3) Optional: auto-start with systemd (only after the manual test succeeds):

```bash
sudo nano /etc/systemd/system/x11vnc.service
```

Paste:

```ini
[Unit]
Description=Start x11vnc at startup
After=display-manager.service
Requires=display-manager.service

[Service]
Type=simple
ExecStart=/usr/bin/x11vnc -display :0 -auth guess -forever -shared
Restart=on-failure

[Install]
WantedBy=graphical.target
```

Enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now x11vnc
```

## Contributing

Feel free to open pull requests or issues. Any improvements to multi-monitor detection, new overlay features, or theming are welcome.

**Enjoy EchoView!**

