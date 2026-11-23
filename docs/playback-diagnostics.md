# Playback diagnostics and retention

Diagnostics are local to each device. No automatic upload, screenshots, media
copies, extra Spotify API calls, source-file scans or web-page content inspection
are used. They observe existing playback and do not restart players or change
playback settings.

## Storage limit

`viewer.log` is capped at **5 MiB**, with **three** retained copies:
`viewer.log.1` (newest archive) through `viewer.log.3`. Total retained log content
is at most **20 MiB** (20,971,520 bytes), plus an empty coordination lock file.
The oldest archive is replaced automatically. No manual cleanup is needed.
Each entry is also bounded to 8 KiB. Existing oversized active/archived logs are
trimmed on the next write, retaining their most recent bytes.

Python logging, playback diagnostics and the network watchdog share the same
process-safe writer. It opens the active file after acquiring a stable lock, so
rotation cannot strand another writer on a renamed file. Write failures must not
interrupt playback. The updater refreshes an already-enabled network watchdog;
it does not enable one that was disabled.

New playback and event-loop diagnostic reports go only to this bounded file.
Other service output still uses the OS's systemd journal, whose retention is
managed separately by the OS; this feature does not change system-wide journal
settings. Installer/update backups are also separate from these log limits.

The web interface's existing log download retrieves the current log. For older
reports inspect the numbered archives over SSH. Old evidence is deliberately
removed once the retention limit is reached, regardless of device uptime.

## What is observed

- **All modes:** the existing GUI heartbeat reports event-loop pauses. Per-display
  health summaries every 15 minutes record active mode, event/suppression counts
  viewer process memory and observation age. Scheduled playback reports its active media mode.
- **mpv video and streams:** a private local Unix socket is sampled every two
  seconds, from a background thread. Only allowlisted `get_property` queries are
  sent. Reports cover cache pauses, increases in output/decoder frame drops and
  late frames, timeline lag of at least 0.75 seconds between samples (adjusted
  for playback speed), an unchanged timeline for at least six seconds, delayed
  startup, unavailable telemetry and unexpected player exits. Paused playback,
  cache pauses, EOF and seeks are excluded from timeline-stall detection. New
  players reset previous observations. Samples must match the expected player PID;
  clip handoffs and single missed replies do not trigger telemetry warnings.
  Three consecutive failed samples after the startup grace period are needed.
  Missing timeline data at EOF is not reported as a new startup. Stale GUI
  observations are excluded. Unsupported counters are ignored.
  Reports identify the player and a bounded local filename/hashed clip reference;
  stream URLs are replaced by a hash. Resolution, frame rate and hardware-decoder
  metadata are queried once playback starts. Drop counts accumulate across
  suppressed reports with their actual observation interval. Problematic clips
  receive a rate-limited summary when the player changes.
- **Qt video/HLS:** existing error/buffering signals and playback-position
  observations are used. Intentional pauses and EOF do not count as stalls.
- **GIFs:** after animation has been observed, frame callbacks update an expected
  deadline using the GIF's own frame delay. A frame over two seconds overdue is
  checked directly on the GUI thread and reported through the bounded queue.
  Worker snapshots are never used to infer a missed GIF deadline. Deliberately long frames are respected; no extra decoding or frame
  counting is requested.
- **Images and image-based fallback:** missing/corrupt media, load/check completion
  taking at least one second and pending loads over five seconds are reported.
  Pending requests superseded by a mode change are excluded. A successfully
  displayed still image is never considered stalled merely because it is still.
- **Spotify:** existing fetch results report request failures, rate limits or needed
  authorization; a local fetch pending over 30 seconds is reported. Pausing music
  or using normal fallback is not a frozen display, and no extra API polling occurs.
- **Chromium/Qt WebEngine:** unexpected browser exits, Qt renderer termination,
  failed embedded-page loads and embedded loads pending over 30 seconds are
  reported. URLs, cookies and raw browser stderr are not copied into diagnostics.
- **Empty/invalid media selections and schedules:** existing unavailable-playback
  states are reported. Calibration/static content relies on the GUI heartbeat.

Repeated issues are limited to one report per category/display per minute.
Queues and category histories are bounded; saturation drops diagnostic messages
rather than delaying playback. Healthy operation writes only occasional summaries.
IPC operations have a 250 ms overall budget and bounded replies. One socket per
configured display is reused across clips/restarts in private temporary storage,
and removed on normal window shutdown; it does not create a file per video.

## Interpretation and limits

An advancing player position does not prove every decoded frame reached the
monitor. Dropped/late-frame counters are evidence of playback trouble, not proof
of its cause; display timing and decoder behavior can affect them. A very short
freeze may occur between samples without being detected. Likewise, an alive
Chromium process does not prove a remote page is updating correctly. There is no
continuous screenshot comparison or new automatic recovery action.

mpv property semantics follow its [official manual](https://mpv.io/manual/stable/).
Diagnostics failing or being unavailable must leave normal playback working.

## Validation

`pytest` covers rotation, oversized-log migration, concurrent process writers,
write failures, bounded queues/rate limits, playback-state exclusions and the
read-only IPC protocol. `tests/native/check_playback_diagnostics.py` exercises real
mpv IPC with generated media, null video/audio output and no NAS access. Existing
native viewer checks cover GIF/image loading, schedules, Spotify, overlays and
live settings with the observers enabled.

## Raspberry Pi video scaling

On Raspberry Pi, mpv uses explicit bilinear luma, chroma and downscaling filters.
This avoids expensive multi-pass resizing on the shared GPU; it can look slightly
softer than convolution filters when resizing. Direct video, scheduled video and
mpv streams share this policy. Image/GIF rendering and desktop mpv defaults are
unchanged. Hardware detection is cached and does not inspect source media.

A live Pi 4 comparison on the same 1440×1080 H.264 clip recorded 61 output drops
in 10 seconds with the existing filters, versus zero in 15 seconds with bilinear
filters. This is a short comparison for that clip, not a guarantee for all media.

Pi mpv playback also has a **24 fps ceiling**. A small bundled player script
observes the source frame rate and adds a labelled FFmpeg `fps=24` filter only
above 24 fps. At 24 fps or below, or when the source rate is unknown, the filter
is absent. File/track changes re-evaluate the limit and retain unrelated filters.
Frames are discarded before rendering without changing playback speed, audio
timing or source files; decoding still processes the source video. This avoids
forcing low-rate content up to 24 fps. GIF/image rendering is unchanged.

The [FFmpeg fps filter](https://ffmpeg.org/ffmpeg-filters.html#fps) performs
frame-rate conversion; this does not use a container frame-rate override.
`tests/native/check_video_fps.py` checks 12, 23.976, 24, 25, 30 and 60 fps
synthetic clips with real mpv, including same-player transitions and normal speed.

## Video picker previews

The specific-video picker requests a cached 256×144 poster only for visible
cards. Hover or keyboard focus requests a four-frame JPEG contact sheet sampled
at 10%, 35%, 60% and 85% of the clip. Animation runs in the browser only while
the card is hovered/focused; reduced-motion preferences disable it. There are
no browser video players, audio streams or continuous frame capture.

Extraction reads selected media without changing it, using one background worker
and low-priority, single-threaded FFmpeg processes. Each probe/frame extraction
has a timeout; duplicate requests share work, and the queue and failure history
are bounded. Leaving the picker or hiding the tab cancels browser requests and
preview timers; an extraction already running can finish and populate the cache.

Generated JPEGs live in `.video-preview-cache` under the application directory,
never on the media share. Retention is capped at **20 MiB and 128 JPEGs**; oldest
entries are removed after generation. Source size/mtime changes invalidate cached
previews. Interrupted temporary files are cleaned on the next completed job.
These limits are separate from the bounded diagnostic logs.
