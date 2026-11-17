# Performance and reliability review

Reviewed local `dev`, November 2026. Hardware measurements remain pending.

## Implemented

- Configuration saves write and sync a temporary file in the configuration
  directory, then replace the live file. Readers see complete JSON; serialization,
  sync or replacement failures preserve the previous configuration and remove
  the temporary file. New files have owner-only permissions, appropriate for
  stored Spotify credentials. This does not serialize concurrent read/modify/write
  operations or guarantee recovery from every power-loss scenario.
- Aspect classification uses a shared per-process LRU cache capped at 2,048
  entries, keyed by absolute path and file identity, size and nanosecond change
  timestamps. Unchanged files avoid repeat Pillow inspection and ffprobe
  processes. Replacement and deletion are detected on the next lookup; the
  viewer no longer retains stale classifications in its own unbounded cache.
- ffprobe inspection has a five-second timeout and returns the existing
  `unknown` classification on failure. Unknown results are cached until file
  metadata changes, eviction or process restart. First inspection of a large
  collection can still take time.
- Browser stats polling skips hidden tabs and pages without a stats panel,
  prevents overlapping requests and refreshes when the tab becomes visible.

These use existing dependencies. Python documents atomic successful
[os.replace](https://docs.python.org/3/library/os.html#os.replace) on POSIX and
[subprocess timeouts](https://docs.python.org/3/library/subprocess.html#subprocess.run),
which kill and wait for the child. The temporary file stays on the destination
filesystem to allow atomic replacement.

## Prioritized follow-ups

1. Media management: routes currently join user-supplied paths directly, uploads
   save directly to final destinations, and rename/move operations can overwrite
   existing files. Add consistent containment checks, explicit collision feedback
   and staged uploads, with route-level tests before changing these behaviors.
2. Thumbnails: bound requested sizes, avoid cache-name collisions such as
   `a/b.jpg` versus `a_b.jpg`, close Pillow images explicitly and publish generated
   thumbnails atomically. These matter most for larger collections and parallel
   browser requests.
3. Stats requests still spend 0.4 seconds sampling CPU. A shared periodic sampler
   could remove this delay. Simply switching to `cpu_percent(interval=None)` in
   request threads risks meaningless first samples; see
   [psutil documentation](https://psutil.readthedocs.io/stable/#psutil.cpu_percent).
4. Validate the pinned runtime on the selected Raspberry Pi OS Trixie ARM64
   target before changing dependencies. The local environment passes `pip check`,
   but this does not verify ARM wheels, display drivers or hardware decoding.
   Follow the existing `runtime-compatibility.md` hardware checklist and
   [Qt for Python installation guidance](https://doc.qt.io/qtforpython-6/gettingstarted.html).

## Validation

- Headless pytest suite: 277 passed (271 before this increment).
- Regression coverage: complete JSON publication, failure cleanup and preservation,
  cached metadata reuse, replacement/deletion invalidation and ffprobe timeout.
- JavaScript syntax check and Node VM checks for hidden/missing panels,
  overlapping requests and resuming after request completion.
- Dependency consistency: `pip check` reports no broken requirements.
- Still needed on Pi: representative image/video playback, CPU/RAM observations,
  controller responsiveness, and settings changes during playback.
