# Output resolution and physical display aspect

The controller's **Display output** section now separates the actual X11 output
mode from its saved preference. Each connector has its own resolution/refresh
selector and physical display-aspect selector. The existing media Aspect Filter
still chooses eligible files; it does not set the display's shape.

## Resolution and refresh

Choose an advertised mode such as `1920x1080 @ 60.00 Hz`, or **Automatic /
preferred mode**, then use **Apply output settings**. The controller applies the
mode through XRandR, re-queries the output and only saves the preference after
successful verification. It then restarts the viewer; a restart failure is
reported separately from a successful output change.

Custom modelines, arbitrary dimensions and framebuffer scaling are not offered.
The list comes from the connector itself. RCA remains an SD PAL/NTSC output;
an HDMI resolution cannot be selected for RCA. Choose the PAL/NTSC boot profile
with the [boot helper](composite-video.md), then select only modes the current
connector advertises. The controller does not switch boot profiles or TV norms.

Commands use argument arrays and bounded timeouts. A command/verification failure
requests the previous mode again and leaves the saved preference unchanged. If
the rollback command also fails, the controller reports that recovery is needed.
Software verification establishes the driver's reported mode, not a visible,
stable signal on the TV. Keep access to the web controller or SSH during eventual
hardware testing. No electrical output tests were performed in development.

The viewer reapplies an explicitly saved mode at startup and when the connector
returns. An unavailable saved mode is logged and left saved for later use; the
current working output is used instead. Automatic settings leave startup mode
selection to the OS. Legacy `chosen_mode` values were previously display-only,
so migration retains them without silently activating them as output preferences.

## Physical aspect

Options are **Auto**, **4:3**, **16:9**, **16:10** and **1:1**. They describe the
physical screen, not the shape of the media. No new Fit/Fill/Stretch control is
added, following the requested scope.

Auto assumes 4:3 for recognized Composite/TV/VEC connector names; other connectors
use square pixels. Set an explicit value for a widescreen CRT or an unusual
output name. Match the TV's own aspect setting to this physical interpretation.

The correction compensates for non-square output pixels. For example, square
artwork occupies 540×576 raster pixels on a 720×576 PAL 4:3 screen, yielding a
physical square. The same logic handles NTSC and HDMI raster/aspect combinations.
Images, animated GIFs and Spotify artwork use corrected dimensions; rotation is
applied before fitting. Embedded video is fitted using the video sink's source
size. Local and external-player video receives the physical monitor aspect
through [mpv's monitor-aspect option](https://mpv.io/manual/stable/#options-monitoraspect).

Web pages/external Chromium use the output raster and are not stretched by this
media correction. Qt clocks/track labels now receive pixel-aspect font correction.
[Presentation settings](presentation-settings.md) provide overscan insets, a
calibration pattern and the optional Pi 3 resource profile. Content already anamorphic needs
its source display aspect interpreted correctly by the video decoder; that still
requires real-stream hardware validation.

## Connector identity and reconnection

Controller, viewer and diagnostics share the XRandR parser. It handles missing
EDID, current/preferred rates, connected-but-inactive outputs, disconnected
outputs and negative positions. `/list_monitors` reports actual connectors and
geometry instead of a fabricated 1080p Display0.

Settings are retained when an output disappears or discovery fails. A lone
legacy Display0/default can migrate to a single unambiguous connector; ambiguous
legacy settings remain stored. The viewer matches Qt screens by connector name,
with a unique HDMI-A-N / HDMI-N alias, rather than list order. Duplicate/ambiguous
screen identities are skipped instead of arbitrarily selecting a screen.

On removal, the associated viewer closes and stops its playback. Reconnection
creates one window on that connector while retaining its configuration. External
video also uses connector-name screen selection; window-manager/backend behavior
still needs testing on the target X11 session. Connectors are the identity: the
settings stay with the port rather than following a TV moved to another port.

## Development verification

- Unit fixtures cover HDMI/composite, no EDID, interlaced mode names, rates,
  inactive/disconnected outputs, negative positions and screen reordering.
- Mode application, validation and rollback are exercised with fake commands;
  no real host display modes changed.
- Controller tests verify actual/preferred distinctions, saved settings only
  after success, invalid input, unavailable modes and service-restart failure.
- Real offscreen Qt checks passed for screen binding, PAL square artwork/GIFs,
  rotation and embedded 16:9 video fitted to a PAL 4:3 raster (720×432 at y=72).
- Real HDMI/RCA timings, hotplug, TV shape, overscan, audio and video signal
  stability remain deferred to the later hardware test session.
