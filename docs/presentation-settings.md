# CRT safe areas, text and resource settings

Each display has a **Safe area and performance** form on the controller. It is
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

**Standard** remains the default. **Pi 3 low resource** is an explicit per-display
choice, not automatic hardware detection. Switching back restores the standard
policy without rewriting the saved global effect settings.

| Setting | Standard | Pi 3 low resource |
| --- | --- | --- |
| Background blur | Saved global setting | Disabled |
| Image preloading | Saved count, bounded to 2 | Disabled |
| Cache entry count | Saved count, bounded to 100; default 15 | At most 4 |
| Cached decoded-image bytes | At most 128 MiB per display | At most 32 MiB per display |
| Decoded image pixel budget | 16,777,216 pixels, side at most 8192 | 921,600 pixels, side at most 1920 |
| GIFs | Animated | First frame only |
| Spotify progress repaint interval | At least 50 ms; default 200 ms | At least 500 ms |
| Extracted video format request | Existing selection | At most 480p |
| External video decoder threads | Existing default | 2 |

The extracted-video request applies to mpv's youtube-dl/yt-dlp path. Local files
and direct HLS streams retain their source resolution; this profile does not
transcode them. Extraction prerequisites and broader stream-format selection
remain plan step 8. It does not guarantee successful playback or a target FPS on
an actual Pi 3.

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
3,680,100 under Pi 3, with the same source retained on disk. Pi 3 GIF playback used
the first frame without constructing an animation player.

These are x86_64 development observations. CPU usage, whole-process memory,
GPU/audio behavior, external-player/window-manager placement, CRT overscan and
PAL/NTSC signal quality still need the deferred Pi hardware session. Calibration
adds no boot edits or reboot. Presentation saving restarts only the viewer;
restart failure is reported separately from successful settings persistence.
