# Runtime compatibility and validation

The selected Raspberry Pi target is **Raspberry Pi OS Trixie 64-bit**, Python
3.11–3.13, glibc 2.39+, X11/Openbox and full KMS. This supersedes the initial
Bookworm candidate: PySide6's ARM64 wheels require glibc 2.39+, whereas Bookworm
provides an older runtime. The installer checks compatibility before modifying
packages, services, boot files or application configuration. It does not upgrade
an OS or migrate X11/Wayland automatically.

| Environment | Validation |
| --- | --- |
| Ubuntu 24.04 x86_64 / Python 3.12 | Clean virtualenv install, full headless suite, dependency consistency, native Multimedia/WebEngine imports and real offscreen viewer/queued-signal smoke check |
| Raspberry Pi OS Trixie ARM64 / Python 3.13 | Selected installation target; compatibility rules covered by fixtures; actual install, update and display/playback checks pending |
| Bookworm ARM64 / 32-bit ARM | Rejected by preflight; requires a separate native-package or source-build strategy |

Sources: [PySide6 wheel metadata](https://pypi.org/project/PySide6/6.12.0/#files),
[Qt's platform/glibc guidance](https://doc.qt.io/qt-6/supported-platforms.html),
[Raspberry Pi OS](https://www.raspberrypi.com/documentation/computers/os.html).

## Dependency layout

- `requirements-base.txt`: exact controller/shared runtime versions.
- `requirements.txt`: base plus PySide6 6.12.0.
- `requirements-dev.txt`: base plus pytest, allowing headless development without Qt.
- `constraints.txt`: resolved transitive versions from the clean development
  environment, shared by all requirement entrypoints. Constraints do not install
  unused packages. These pins improve repeatability but are not a hash-locked
  or hardware-validated ARM distribution.

The selected runtime uses Flask 3.1.3 / Werkzeug 3.1.9, Spotipy 2.26.0,
requests 2.34.2, psutil 7.2.2 and Pillow 13.0.0. The previous Flask test-client
workaround is removed. Optional YouTube playback uses `requirements-streaming.txt`; see [streaming](streaming.md).

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check
```

For a full viewer environment, additionally install `requirements.txt` and run:

```bash
.venv/bin/python -m echoview.runtime_check --qt
```

This native check imports the real Qt modules in a separate process, independently
of the headless test stubs. It does not launch a GUI or contact Spotify. It cannot
prove X11 plugin readiness, hardware decoding, audio output or Chromium playback.
For the automated installation target, preflight alone can be run without sudo:

```bash
python3 echoview/runtime_check.py --installer
```

## Installer changes and recovery

Setup uses the target's actual native library names, including Trixie's `t64`
packages, and requires binary Python packages. Missing pins, unsupported wheels,
pip failures, inconsistent dependencies or Qt import failures stop setup before
it writes service/configuration updates. It no longer creates libwebp, libtiff or
libminizip ABI symlinks. Previously created links are not automatically deleted:
inspect their ownership and package provenance on the actual device first.

Auto-update reads `.env` from the checkout being updated and requires it to exist.
Custom viewer/media/token paths remain intact, and environment contents are not
printed. Failure tests use fake executables and fixture files: no real systemd,
apt, boot configuration or services were modified during development validation.
Update failure reporting and recovery are described in [update recovery](update-recovery.md).

On this development host, native imports initially identified missing libEGL.so.1
and libxkbfile.so.1. Matching Ubuntu packages were downloaded and extracted only
under `/tmp`, then used through a process-local `LD_LIBRARY_PATH` for validation.
No host apt packages were installed and no system libraries were linked. The
real offscreen viewer constructed successfully and delivered a mocked Spotify
worker result on the GUI thread. Offscreen GPU/audio/PipeWire warnings are
expected here; they do not establish working hardware rendering or audio.

Remaining release checks: real Trixie/Pi 3 fresh install, configuration-preserving
upgrade, X11 login/startup, live Spotify exchange and refresh, HDMI playback and
later composite PAL/NTSC validation. An existing Bookworm device should be backed
up and migrated deliberately to a compatible image; do not assume auto-update
will make its glibc compatible.

Pi 3 B+ Trixie Lite hardware bring-up identified an additional native requirement:
`pipewire-bin` supplies `/usr/share/pipewire/client.conf` and pulls in the matching
PipeWire modules. Having only `libpipewire-0.3-0t64` was insufficient: creating
Qt audio objects crashed with missing client configuration. Setup now installs
`pipewire-bin` explicitly. This fixes viewer initialization; a working audio server
and audible output are separate hardware checks.
