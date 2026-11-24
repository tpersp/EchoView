# Playing media and saving setups

## From Media to a display

Open a folder in Media, choose the target display beneath a file, and press
**Play on display**. The selection applies without leaving the folder. The last
target display is remembered for the browser session. A folder also has
**Play this folder on a display** controls for image/GIF slideshows or videos.

- An image or GIF uses Specific Image/GIF mode.
- An individual video uses Videos mode with that filename selected. It repeats
  using the normal video playback controls, without scanning the other videos.
- Playing a video folder clears the individual-video selection.
- The chosen display's saved volume, mute, rotation and output preferences stay
  in place. Explicit file selection sets its aspect filter to Any so the selected
  file cannot silently be filtered out. Folder playback uses the current filter.
- Only the chosen display's playback settings change. Applying currently
  restarts the viewer service, so playback on other displays can briefly restart.

These actions update local configuration and read media for playback. They do
not move, rename, edit or delete source media, including NAS files.

In Displays, **Video selection → All videos in folder** restores folder playback.
Choosing another video category clears a selection from the previous category.
Unavailable folders remain visible and selected rather than being replaced
with All when a NAS mount is temporarily missing.

## Display presets

Apply the display setup you want, then open **Saved display presets**, enter a
name and choose **Save applied setup**. Save is disabled while the page has
unsaved display changes. Presets capture the applied configuration, not a draft
form, a copy of the media files, or the current position within a slideshow.

Choose a preset and press **Apply preset** to restore it. Supported playback
settings include media modes, folders, selected files, filters, shuffle,
rotation, local-video audio settings, Spotify display preferences and web URLs.
Physical resolution, display aspect ratio, safe area, resource profile, theme,
global overlay and credentials are preserved. Known HDMI connector aliases are
matched; a preset with no matching configured displays gives an explanation.

Up to 20 presets are stored in the existing private configuration file. Names
must be distinct, including case; saving never silently overwrites an existing
preset. Delete removes only the saved setup and leaves playback and media alone.

## Applying and recovering

Changing modes retains the mixed-folder list and video category/selection.
Mixed-folder drag ordering is saved as the actual item order; JSON form values also
preserve folder names containing commas. Older comma-separated forms remain
accepted for ordinary folder names.

Applying an unchanged setup does not save again or interrupt playback. Failed
configuration writes do not restart the viewer. If settings save but restarting
cannot be confirmed, the page distinguishes that state and offers recovery
through the existing Restart Viewer action and service logs. Missing direct-play
files are rejected before saving or restarting. There is no automatic retry that
could unexpectedly interrupt playback later.

## Validation and release scope

The automated suite covers settings preservation, no-op Apply, save/restart
failures, invalid or missing media, path containment, preset limits and restore
behavior, connector aliases, and single-video selection. Chromium checks use
synthetic media and simulated restarts for the complete save/play/restore flow,
including real drag ordering. A separate check with the Pi's native Qt runtime
verifies single-video playlist construction, whole-folder restoration and
missing-file handling without starting playback or touching NAS files:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/native/check_single_video.py
```

Before promoting dev to main, manually exercise direct image/GIF and selected
video playback over HDMI, return to folder playback, save/apply a preset and
verify persistence after a normal reboot. Multi-display playback interruptions
and the existing Pi 3/composite validation checklist remain separate hardware
checks. The automated native check verifies selection, not HDMI video decoding.
