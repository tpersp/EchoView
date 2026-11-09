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

Automated setup targets **Raspberry Pi OS Trixie 64-bit** (Lite or Desktop) with
**X11**, Python 3.11–3.13 and glibc 2.39+. Pi 3 hardware validation remains
pending. Bookworm ARM64 and 32-bit images are rejected before setup changes the
system. See [runtime compatibility](docs/runtime-compatibility.md) before updating an existing device.

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
- **Native Qt/WebEngine dependencies** are installed using Trixie package names.
  Setup verifies Multimedia and WebEngine imports without creating ABI symlinks.
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

### YouTube and streaming

YouTube playback resolves the original URL through mpv and the optional pinned
streaming stack, including yt-dlp, its JavaScript helpers and Deno. Install with
`sudo ./setup.sh --with-streaming`. Without that stack, EchoView uses an embedded
player served by the local controller. External Chromium is an explicit display
option. Direct HLS continues through Qt Multimedia.

Sources are resolved again on retries rather than saving expiring YouTube media
URLs. Video quality follows the selected display setting in every resource profile. See [streaming setup and recovery](docs/streaming.md)
for installation checks, fallback behavior and remaining hardware validation.

Qt WebEngine defaults to `--autoplay-policy=no-user-gesture-required`, using its
actual browser identity and GPU defaults. Custom flags remain configurable through
`QTWEBENGINE_CHROMIUM_FLAGS` and `ECHOVIEW_CHROMIUM_FLAGS` for external Chromium.

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
Auto-update requires the existing checkout's `.env`; its `VIEWER_HOME`,
`IMAGE_DIR` and other values are preserved. The viewer user is resolved from
`VIEWER_USER`, the installed service, or the sudo caller, rather than assuming
`pi`. Unsupported platforms fail before package/service/boot changes.

## Troubleshooting

- **No images?** Ensure images exist in the `IMAGE_DIR` (or subfolders). By default, check `/mnt/EchoViews` or wherever you mounted.
- **Wrong screen**? Confirm you have multiple monitors recognized by X. EchoView uses PySide6’s screen geometry, so make sure your environment is not on Wayland.
- **Spotify issues**? Check the file specified by `SPOTIFY_CACHE_PATH` for the saved token. Re-authorize if needed.
- **Overlay not transparent?** You need a compositor (like **picom**) running for real transparency.
- **Web viewer blank?** Run `.venv/bin/python -m echoview.runtime_check --qt`.
  Resolve missing native packages using the supported OS image; do not create
  cross-major library symlinks. Existing manually created symlinks need inspection
  before removal; setup does not delete system libraries.
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


## Read-only runtime diagnostics

Run this with the same Python environment as EchoView (normally `.venv`):

```bash
.venv/bin/python -m echoview.diagnostics
```

The JSON report includes OS/architecture, Python and installed package versions,
connector geometry, available browser/media tools and service activity. It does
not read application configuration, `.env`, Spotify tokens, service environments
or logs, and omits hostnames, IP addresses and executable paths. Missing tools,
headless sessions and unavailable systemd checks are reported without failing.
Each subprocess probe has a five-second timeout. No GUI or playback is started.
Service activity is not an application-readiness check; the Qt platform shown is
the requested backend, not a verified running backend.

The initial hardware validation target is **Raspberry Pi 3 B/B+, Raspberry Pi OS
Trixie 64-bit, X11/Openbox with full KMS**, first over HDMI and then composite
PAL and NTSC. This is a selected test target, not yet a supported configuration:
Qt wheel/native-library compatibility, real Spotify authorization and RCA output
remain to be validated on hardware. Bookworm ARM64 cannot use the selected wheels because of glibc requirements;
32-bit images and other OS versions need a separate packaging approach. The development-host report is in
`docs/diagnostics-development-host.json`; it is not evidence of Pi compatibility.

### Spotify authorization from another computer

Register the exact callback URL in the Spotify Developer Dashboard. EchoView
requires both `user-read-currently-playing` and `user-read-playback-state`.
Spotify accepts HTTPS callbacks, or HTTP with an explicit loopback IP such as
`127.0.0.1` or `[::1]`; `localhost` and HTTP LAN callbacks are not accepted.
See [Spotify's redirect requirements](https://developer.spotify.com/documentation/web-api/concepts/redirect_uri).

For a laptop browser without an HTTPS controller address:

1. Run `ssh -N -L 8080:127.0.0.1:8080 user@PI-IP` on the laptop.
2. Open `http://127.0.0.1:8080/configure_spotify` in that browser.
3. Save `http://127.0.0.1:8080/callback` as the redirect URI, matching the Dashboard.
4. Start authorization and keep the tunnel open through the callback.

Alternatively access the controller through an HTTPS reverse proxy and register
its `/callback` URL. Begin and finish on the same controller address and browser;
do not manually rewrite callback addresses. Authorization attempts expire after
ten minutes and can only be used once. A new authorization attempt in the same
browser replaces the previous attempt.

The controller creates a private `.oauth_state.sqlite3` file in `VIEWER_HOME` for
its persistent signing key and pending authorization states. The service user
must be able to write there. Removing this file invalidates browser sessions and
pending attempts, but does not delete the Spotify token cache. Changing Spotify
credentials, scopes or callback settings deletes the old token cache and requires
reauthorization.

The status page checks token structure, expiry and scopes without making network
requests. **Check Connection** additionally validates/refreshes the cached token
through Spotipy and calls the playback API; no active playback is a successful
connection result. Revoked tokens, network failures and access/quota errors can
only be established by this live check. For access denial, check Dashboard allowed
users, requested scopes and the development app owner's Premium subscription.

### Spotify display polling

All Spotify windows in one viewer process share serialized playback polling and
token validation/refresh. Requests run on background workers; only queued Qt
results update widgets. Reloading settings or closing a window invalidates its
outstanding result. Polling is limited to one API request per five seconds for
the process, independently of the local progress-bar timer and fallback-image
interval. Provider rate limits and errors lengthen this delay; `Retry-After` is
honored, and quota exhaustion uses a minimum five-minute pause. Authorization
and access failures retry after one minute; network errors use bounded backoff.
These statuses are logged without provider exception details.

Tracks and episodes can display metadata even when artwork is missing. Paused,
unavailable and failed playback use the configured fallback. Artwork is reused
by URL, limited to eight images of at most 4 MiB and 4096×4096 pixels each, and
stored in a temporary directory cleaned on normal process exit. Interrupted
or forcibly killed processes may leave their temporary directory behind.
Repeated failed artwork requests are throttled. The controller's manual
connection check is a separate process and is not part of viewer polling.

## Composite / RCA video on Raspberry Pi 3

Setup preserves the current output by default. Select `--video-profile hdmi`,
`composite-pal` or `composite-ntsc` explicitly to change it. Preview first:

```bash
bash setup.sh --video-profile composite-pal --dry-run
```

The standalone `python3 -m echoview.boot_profiles` helper can apply or restore
boot profiles without running installation. Every change saves a verified backup;
PAL/NTSC output still requires Pi hardware validation. See
[composite setup and recovery](docs/composite-video.md) for commands, cable
requirements, offline-card recovery and the current Pi 3 scope.

## Resolution and display aspect

Use **Display output** in the web controller to select an advertised resolution
and refresh rate, plus the physical screen shape (Auto, 4:3, 16:9, 16:10 or 1:1).
The page shows the actual mode separately from the saved preference. RCA is
limited to the SD modes exposed by its current PAL/NTSC profile.

Disconnected outputs retain their settings, and viewer windows follow connector
names across reconnection. See [display settings](docs/display-settings.md) for
aspect correction, video/browser limits, mode recovery and pending hardware tests.

## CRT safe area and Pi 3 resource profile

Use **Safe area** to inset each edge by 0–20% without changing
resolution. Clocks, track text and progress stay inside the visible area, with
font-width correction for non-square pixels. **Calibration Pattern** mode shows
a grid, inset marks and a circle for the later TV test.

The device-wide **Pi 3 low resource** profile in **Settings → Device performance** disables blur/preloading and reduces
image/cache budgets while preserving GIF animation and normal video playback. Standard
remains the default. See [presentation settings](docs/presentation-settings.md)
for the tradeoffs, external-browser limits and development measurements.

Update failure handling, private backups and service startup checks are documented in
[update and recovery](docs/update-recovery.md).

Audio services, output selection and silent-playback troubleshooting are covered
in [audio setup](docs/audio.md).
