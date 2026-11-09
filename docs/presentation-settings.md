# CRT safe areas, text and resource settings

Each display has a **Safe area** form on the controller. It is
separate from the resolution/aspect form: saving presentation settings never
requests a different output mode. Settings can also be saved for a disconnected
output and will be used when it returns.

## Safe area and calibration

Set left, right, top and bottom insets as percentages from 0 to 20. They default
to zero, preserving the full raster. For example, 5% on every edge of a 720×576
PAL raster produces a 648×518 content region beginning at (36, 29). Black margins
surround the content. Insets are independent of the physical pixel-aspect
correction; the visible picture retains its intended shape.

The content region contains images, GIFs, Spotify artwork, embedded pages/video,
clocks, track text and progress. Progress placement reserves space around track
text and is clamped inside the content bounds. Clock/track font widths compensate
for non-square pixels; clock text is reduced if needed to fit. Font sizes are
also constrained by the available height. Large clock sizes up to 512 are accepted
for larger HDMI displays; SD layouts apply an appropriate local cap.

Choose **Calibration Pattern** in the viewer's Mode selector and save. It shows
the content border, 5%/10% inset marks, a grid and a circle. The pattern follows
the safe area and selected physical display aspect; the circle should look round
on the TV. In a raw PAL/NTSC screenshot viewed with square pixels, the circle can
look slightly oval because the raster has already been corrected for the TV.
An enabled clock remains available for text placement checks. Choose the previous
viewer mode to leave calibration.

External mpv playback receives the same percentage video margins and physical
monitor aspect. External Chromium receives inset window position/size requests,
but its kiosk/fullscreen window manager may ignore them. Embedded web views obey
the content bounds; webpage pixel-aspect stretching is not applied. External
players/browser windows do not acquire Qt clock or track overlays.

Sources: [mpv video margins](https://mpv.io/manual/stable/#options-video-margin-ratio-left),
[Qt image-reader scaling](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QImageReader.html).

## Optional Pi 3 profile

**Standard** remains the default. **Pi 3 low resource** is an explicit device-wide
choice, not automatic hardware detection. Switching back restores the standard
policy without rewriting the saved global effect settings.

| Setting | Standard | Pi 3 low resource |
| --- | --- | --- |
| Background blur | Saved global setting | Disabled |
| Image preloading | Saved count, bounded to 2 | Disabled |
| Cache entry count | Saved count, bounded to 100; default 15 | At most 4 |
| Cached decoded-image bytes | At most 128 MiB per display | At most 32 MiB per display |
| Decoded image pixel budget | 16,777,216 pixels, side at most 8192 | 921,600 pixels, side at most 1920 |
| GIFs | Animated | Animated |
| Spotify progress repaint interval | At least 50 ms; default 200 ms | At least 500 ms |
| Extracted video format request | Display quality selection | Display quality selection |
| External video decoder threads | Existing default | 2 |

All resource profiles retain GIF animation, normal video playback and the chosen
stream quality. Local files and direct HLS streams retain their source resolution;
this profile does not transcode them. See [streaming](streaming.md) for extraction
prerequisites. Actual playback performance still depends on the media and hardware.

Cache limits count stored decoded QImages, not total application memory. The
currently displayed pixmap, render buffers, decoder temporary allocations, Qt,
video and browser processes use additional memory. Some image plugins must
internally decode their source before resizing, so the decoded-output budget is
not a strict transient decoder-memory limit. Very large or unsupported images
can still fail to decode and will show an image-error message.

Image preloading now caches QImage data instead of creating QPixmaps on worker
threads. Pixmap conversion stays on the GUI thread. Cache eviction follows both
entry and byte limits, and results from an older profile generation cannot refill
a newly cleared cache. In-flight preloads are bounded; Pi 3 creates none.

## Development results and remaining checks

The headless suite covers invalid/non-finite margins, asymmetric safe bounds,
text containment, aspect font stretch, decoded-image sizing, cache eviction and
profile-generation races. Controller tests verify that these settings do not
change resolution and that invalid settings are not saved.

Real offscreen Qt checks passed for PAL safe bounds, pixel-correct clock fonts,
large/difference-mode clock text, wrapped track text with a separate progress bar,
inset embedded video, calibration rendering and standard animated GIF playback.
A 6000×4000 JPEG produced 67,094,016 decoded-cache bytes under Standard and
3,680,100 under Pi 3, with the same source retained on disk. Both profiles use
the normal GIF animation player; cache savings do not disable playback.

These are x86_64 development observations. CPU usage, whole-process memory,
GPU/audio behavior, external-player/window-manager placement, CRT overscan and
PAL/NTSC signal quality still need the deferred Pi hardware session. Calibration
adds no boot edits or reboot. Presentation saving restarts only the viewer;
restart failure is reported separately from successful settings persistence.

Calibration Pattern also includes seven nominal 75% RGB colour bars and an
independent eight-step white-to-black grayscale ramp. The latter remains useful
on monochrome CRTs. The grid, 5%/10% borders and corrected circle remain present.
A [PAL colour reference capture](assets/echoview-calibration-pal-colour.png) is
saved alongside the original pattern. These bars aid visual checks; they do not
replace a calibrated broadcast signal generator.

Resource profile is selected under **Settings → Device performance** and applies
to all displays. Safe areas, resolution and aspect remain per-display. Existing
per-display profiles migrate once: if any display used Pi 3, the device adopts Pi 3,
unless a valid global choice already exists. Old per-display profile keys are
removed. Saving this setting restarts the viewer; a failed restart preserves the
saved choice and reports that a manual restart is needed.

To verify real GIF decoding and animation independently of the headless unit-test
stubs, install the full runtime and run:

```bash
QT_QPA_PLATFORM=offscreen python tests/native/check_gif_playback.py
```

This uses generated temporary media/configuration and checks looping frames at
normal playback speed under both profiles, including rotation/scaling. Each case
runs in its own Qt process. Restricted development containers may need an explicit
Qt WebEngine sandbox override; that override is not required by this profile.
