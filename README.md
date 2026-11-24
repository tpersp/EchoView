# EchoView

EchoView is a modern, easy-to-configure slideshow + overlay viewer written in **Python/PySide6** along with a companion **Flask**-based web interface. It seamlessly supports multiple monitors on a Raspberry Pi and can optionally display a live overlay (e.g. clock) on top of your images or GIFs.

## Key Features

- **Multiple Monitors**: Launches a PySide6 window per detected monitor, each with its own display mode (Random, Mixed, Spotify, Web Page, etc.).
- **Web Controller**: A Flask web interface (on port **8080**) lets you manage sub-devices, change the slideshow folder, set intervals, shuffle, or pick a single image.
- **Direct Media Playback**: Play an image, GIF, individual video or whole folder on a chosen display from Media, without changing the media files.
- **Display Presets**: Save and restore named playback setups while keeping physical output and device settings. See the [media workflow guide](docs/media-workflows.md).
- **Scheduled Playback**: Set daily start times for image/GIF or video folder groups, with automatic switching on the Pi and a visual schedule editor. See [daily schedules](docs/playback-schedules.md).
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

### Optional network watchdog

The installer can enable automatic network recovery with a primary target (for
example, your NAS) and an optional fallback (for example, the gateway). A reply
from either prevents rebooting; both must fail for the configured consecutive
rounds before the Pi reboots. Existing single-target setups remain supported.
See [watchdog behavior and configuration](docs/network-watchdog.md).

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

In `Configure Spotify`, provide your **Client ID** and **Redirect URI** from the Spotify Developer Dashboard. New connections use **Authorization Code with PKCE**, which does not require a Client Secret. Existing secret-based connections remain supported; select PKCE, save, and authorize again to migrate. Then click **Authorize Spotify** to store the OAuth token. You can set one or more displays to `spotify` mode.

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

The viewer also records event-loop heartbeat gaps of at least 0.75 seconds in
`viewer.log` and the service journal, after the event loop recovers. A background
watchdog checks four times per second; reports are limited to one per 30 seconds.
Reports include the gap and up to eight Python function names/line numbers, never
frame locals, media contents or credentials. Native Qt work may appear only as
the application event loop; this detects pauses but does not by itself identify
their cause. It does not restart playback or change media settings.
If native code permanently holds the Python GIL, the Python watchdog cannot run
either; an external thread-stack capture is needed to investigate that case.

Both the normal image slideshow and Spotify's fallback slideshow preload their
next image using one reusable background worker per display. GIFs up to 32 MiB
(8 MiB with the Pi 3 resource profile) also retain their compressed source bytes
within the existing image-cache budget, so animation playback does not need NAS
reads. This caches encoded data, not every decoded frame. Larger GIFs retain
file-backed playback. Source media is never rewritten by this caching.
Preloading decodes first frames with Pillow and hands detached pixel data to
Qt. Qt image plugins are kept off preload threads to avoid a plugin-lock/Python
GIL deadlock with GIF playback. EXIF orientation and decode-size limits apply.
File-existence checks and cache-miss loading for slideshow and classic Spotify
artwork transitions also run in a background worker. Existing media keeps playing
until the result is ready. Pending requests are bounded to the latest selection;
late results after a mode change or window closure are discarded. A missing file
still displays the existing error message, including when its pixels were cached.

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

PKCE is the default for new connections. Its per-attempt verifier is kept on the
controller, bound to the browser session and saved configuration, and consumed
once at callback. It survives a controller restart during authorization. The
verifier is never sent in the browser cookie. Tokens refresh automatically without
a Client Secret. Existing secret-based connections retain their original method
until explicitly switched; switching deletes the old token and saved secret.

See [Spotify's PKCE flow](https://developer.spotify.com/documentation/web-api/tutorials/code-pkce-flow).
This integration displays now-playing metadata; it does not stream Spotify audio.
For current app-owner Premium and allowed-user requirements, see
[Spotify quota modes](https://developer.spotify.com/documentation/web-api/concepts/quota-modes).

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
interval. Each window follows the shared next-request deadline so API/artwork
latency cannot turn a five-second cadence into a ten-second gap. An expected
track ending can bring the next check forward (with a two-second minimum between
requests); manual skips are detected by normal polling. The progress bar uses
local monotonic-time interpolation and subpixel painting, without extra API
requests. Standard profiles animate at up to 20 frames per second; the Pi 3
profile limits this to two. Small timing corrections blend over two seconds;
new tracks and larger seeks update immediately. Turn off **Smooth progress
animation** under **Progress appearance** to use the previous update interval. Provider rate limits and errors lengthen this delay; `Retry-After` is
honored, and quota exhaustion uses a minimum five-minute pause. Authorization
and access failures retry after one minute; network errors use bounded backoff.
These statuses are logged without provider exception details.

Enable **Elapsed / total time** in a display's Spotify options to show a timer
such as `0:24/3:14`. It works in Classic, Album card and Poster layouts, either
beside the progress bar or on its own. It is off by default, previews before
applying, saves with presets and applies live. The existing local playback
timeline drives both indicators; time-only mode updates once per second without
extra Spotify requests. Long tracks use hours and unknown duration shows a dash.

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

### Spotify layouts and web now playing

In **Displays → Spotify**, choose **Classic** (maximum-size artwork with track details over it),
**Album card** (artwork beside a text panel; stacks on portrait screens), or
**Poster** (centered artwork with track details below). Classic remains the
default. Enable **Playing on device** alongside the title/artist/album toggles to
show the active Spotify device on any layout (off by default; omitted when
Spotify supplies no device name). This uses the existing playback response.
Card and Poster place text and progress automatically, retain text
visibility, size and color settings, and respect output safe area and physical
pixel aspect. Layout selection is included in display presets.

Classic is suited to smaller screens: the cover retains its full available size,
with a compact translucent track panel over the artwork. The title is emphasized;
long fields use an ellipsis rather than covering the screen. Track position, text
size, visibility and manual colours remain configurable. Automatic contrast uses
light text on a dark panel; dark manual text gets a light panel. Its web preview
uses the same cover fit, panel spacing, safe area and progress placement.

**Background appearance** offers **Black**, **Artwork colour**, **Artwork
gradient**, and **Blurred artwork**, plus a **Dimming** slider (0–95%). Black preserves the existing
background for each layout. Artwork colours are extracted from a 48-pixel
thumbnail once per downloaded cover, on the existing Spotify worker, and cached
alongside at most eight covers. Gradients are static; there is no animated effect,
extra Spotify polling, per-frame analysis or NAS access. Missing artwork uses a
neutral palette, and palette-analysis failure never prevents valid artwork from
displaying. Card layouts automatically choose light/dark text when automatic
contrast is enabled; manual text colours remain available.

Blurred artwork fills the screen with a softened, centre-cropped cover. It uses
a cached thumbnail of at most 96×96 pixels and one screen-sized image per active
layout, rebuilt only when artwork, dimming or screen size changes. No continuous
blur effect or extra artwork download runs; a missing cover falls back to black.

Changes preview before Apply, apply live without resetting playback/progress,
and are included in presets. Spotify fallback media retains its normal image or
video appearance. Older presets restore the default background settings.

The **Spotify** web page includes a read-only **Now playing** panel with artwork,
track/episode information, elapsed/total time, device name and shuffle/repeat
status. It reads a small local snapshot produced by the viewer's existing poll;
opening the page does not call Spotify. It needs at least one display in Spotify
mode. Paused playback freezes progress; stale/offline/authorization states are
shown explicitly. Browser polling pauses while the tab is hidden.

Snapshots and up to two 320px artwork thumbnails live in a private temporary
folder identified by the service user and VIEWER_HOME (Linux shared memory when
available, otherwise the system temporary directory). This avoids periodic
SD-card writes on the Pi. Metadata is published
atomically, tied to the current Spotify configuration, and expires after 45
seconds without an update. Tokens and credentials are never included. Source
media and the NAS are not used for these thumbnails. There are no playback
controls and no additional Spotify permissions.

### Previewing and applying Spotify appearance

Open **Displays → Spotify → Preview before applying** to try layout, text size,
color, information visibility and progress appearance. The browser preview uses
the locally cached track/artwork (or an example when nothing is available),
updates while editing, and never saves settings. Placement is approximate;
physical output and image appearance settings still belong to the real display.
Opening a preview adds no Spotify API requests, and local refresh pauses in a
hidden tab.

**Apply to displays** updates Spotify-only visual changes in the running viewer,
including layout, text and progress options. The current window, track,
interpolation timeline, artwork and API polling stay intact. Mode/media changes,
fallback changes and physical output settings retain the normal restart path.
Presets that only change Spotify visuals use the live path too.

The controller saves first, publishes a private local request, and waits up to
three seconds for the viewer's confirmation. The viewer processes it on its Qt
thread and rejects requests superseded by another save. If confirmation is
missing, settings remain saved and the UI says so; it does not force a restart.
Use **Restart viewer** if needed. This channel uses the same private temporary
storage as the now-playing snapshot and never reads NAS media.

### Live clock overlay settings

**Overlays → Apply overlay settings** changes clock visibility, size, color,
automatic contrast and position in the running viewer. It updates the clock
widgets on the Qt thread without reloading media, restarting players, resetting
slideshow timers or changing Spotify progress. Settings for disconnected outputs
are retained for their next connection. Applying unchanged settings is a no-op.
The page confirms live application, or reports that settings were saved but the
viewer could not confirm them. It never forces a restart on confirmation failure.

Each display’s **Overlays** card previews clock edits over a frame from the
running viewer. It fetches one frame by default. Enable **Live** to refresh approximately every two seconds
while the preview is visible; turn it off to hold a frame, or use **Refresh**.
The viewer and preview share a bundled local clock font and use matching text
fitting, so clock width does not depend on the browser’s system font.
The clock uses device time, physical aspect and saved safe area, with manual
colour or difference blending over the actual background. Edits stay in the
browser until Apply; capture never hides or changes the display's real clock.
Browser fonts and downsampling can differ from the physical display.

Images, GIFs and Spotify layouts are rendered from existing viewer pixels with
the clock excluded. Qt video uses its current video-sink frame. External players
use the assigned screen's screenshot support; unsupported capture backends or
hardware video planes can limit those previews. Unavailable/delayed captures are
reported beside the preview, with the last frame retained when possible.

Frames are limited to 640 pixels per side, encoded with Pillow off the Qt thread
and passed through bounded, private shared-memory files (temporary-directory
fallback). The controller serves JPEGs with `Cache-Control: no-store`. Capture
is capped at two per second across clients and occurs only on browser requests;
hidden/offscreen previews stop polling. The preview does not reopen source media,
decode another video, call Spotify, save settings or restart playback.

Clock overlays support **Show seconds** and a per-display **Clock format**:
**24-hour** (`13:05` / `13:05:09`) or **12-hour · AM/PM** (`1:05 PM` /
`1:05:09 PM`). Existing clocks keep 24-hour time with seconds. Format changes
update the preview immediately and apply live. AM/PM is locale-independent;
midnight is 12 AM and noon is 12 PM. Clock width adjusts as the text changes,
keeping right/center alignment without touching media playback.

**Blink separators** optionally flashes the clock’s colons once per second
(half a second visible, half hidden). Digits and AM/PM remain steady, and hidden
colons retain their space so the clock never shifts. It works with either clock
format and with seconds hidden, updates the preview, and applies live. Blinking
is off by default; disabled clocks retain the normal one-second timer.


### Bounded playback diagnostics

EchoView keeps a 5 MiB current log and three rotated copies (20 MiB maximum
retained log content). Old reports are removed automatically, including when
running unattended for years. Existing oversized logs are trimmed on the next
write. Video, GIF, image, Spotify and browser diagnostics use bounded local
reporting without extra media scans or Spotify requests. See
[playback diagnostics and retention](docs/playback-diagnostics.md) for coverage,
limits and validation.


### Recovery status

**Status** shows current playback problems and relevant actions without listing
media or probing the NAS. The Displays page shows the same panel only when
attention is needed. It covers missing storage mounts, slow/failed media loads,
invalid schedules, persistent video buffering/stalls, Spotify authorization or
connection errors, and browser failures. Warnings clear when playback recovers.

Status comes from a bounded local viewer snapshot refreshed every five seconds;
it does not read historical logs or make extra Spotify requests. Mount checks
read local mount metadata only: an offline NAS may remain mounted, in which case
load/buffering problems appear when observed. **Restart viewer** is always an
explicit action and preserves unsaved page edits. No automatic restarts or remounts
are added. A stale or stopped viewer is reported rather than shown as healthy.


### Schedule editor

The schedule editor uses explicit **24-hour hour/minute fields**, independent of
browser locale. Existing slots appear as compact cards; expand a card to edit its
time, media and folders. Folder choices open inline with search, while selected
folders stay in a removable list. The day overview above the cards is unchanged.


Shuffled playback completes the entire selected list before preparing a fresh
order for the next pass, avoiding an immediate repeat at the boundary when there
is more than one distinct item. This applies to images/GIFs, videos and shuffled
Spotify fallback. Reshuffling uses the existing in-memory list, without rescanning
media; image prefetch follows the next pass. Unshuffled playback keeps its order.
Schedule slots still select only their own folders, including overnight carryover.
