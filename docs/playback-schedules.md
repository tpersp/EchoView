# Daily playback schedules

Choose **Scheduled playback** in a display's Mode dropdown. A schedule belongs
to that display and repeats every day, independently of the browser.

1. Add slots, or use the **06:00 / 14:00 / 18:00** example.
2. Give each slot a start time and optional name.
3. Choose Images/GIFs or Videos, then open the folder dropdown. Click a folder
   to add a checkmark; chosen folders appear as removable chips. Search and
   Select results help with larger collections. Shuffle is set per slot.
4. Review the daily timeline and the highlighted slot at the current device time.
5. Set the shared image interval and video preferences below, then Apply.

For example, Morning at 06:00 runs until Afternoon at 14:00; Afternoon runs until
Evening at 18:00; Evening runs through midnight until 06:00 the next morning.
One slot runs all day. Duplicate start times, empty folder selections and
invalid times are rejected. Up to 48 slots are supported.

The preview shows the Pi's local time and UTC offset, even if your browser is in
a different timezone. It refreshes its clock periodically while visible. To
change the schedule timezone, configure the Pi's system timezone; this editor
does not change system time or timezone. Keep the Pi's clock synchronized.

## Playback behavior

- Startup selects the slot that should be active now, including the previous
  evening's slot before the first start time. Missed slots are not replayed.
- A one-second Qt timer checks the current local clock. Media is rebuilt only
  when the active slot changes, rather than being scanned every second. Timing
  depends on the viewer event loop and file-system responsiveness; it is not a
  hard real-time guarantee.
- Slot changes reuse the current viewer window. They do not invoke systemd,
  restart the viewer service, require the web page to stay open, or create cron
  jobs. Saving a changed setup still uses the existing Apply/restart flow.
- At a boundary, the current video is interrupted to start the next slot.
  Within a slot, existing mute/volume and Play to End/maximum-duration preferences
  apply. Rotation and aspect filtering still apply as configured.
- Images/GIFs and videos use the selected folders in selection order, or shuffle
  across the combined list. A scheduled video group ignores a previous manual
  single-video selection without erasing that saved choice.
- Empty/unavailable active groups show the normal no-media message and retry
  every 30 seconds. Unavailable folders remain selected in the editor. A new
  slot still takes over at its time. No source media is changed.
- Daily rules follow local wall time through clock corrections and daylight
  saving changes. A forward jump selects the current matching slot; a backward
  jump re-evaluates the repeated local hour. There is no once-only job state to
  lose during a reboot or clock adjustment.

Selecting another mode or using Media's Play on display overrides scheduling
for that display. Select Scheduled playback again to resume the saved schedule.
Display presets capture and restore the schedule along with playback choices;
physical output and device settings remain separate.

## Verification

Pure timing tests cover exact boundaries, midnight carry, one-slot schedules,
reboot/clock-jump selection and both DST transitions. Route tests cover canonical
saving, invalid input, no-op Apply, preservation when switching modes and atomic
validation across multiple displays. Viewer tests check one transition per slot,
grouped video lists and throttled media recovery.

Chromium checks use synthetic media and simulated viewer restarts to verify the
editor, duplicate-time/empty-folder errors, timeline, a foreign browser timezone,
save/reload, preset restoration and mobile layout. The native Qt check uses
temporary images/GIFs and an injected clock; it does not start video playback or
touch the live media collection:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/native/check_schedule.py
```

Before a main release, also verify an actual scheduled HDMI transition while
playing a video, including the desired boundary interruption and audio behavior.
An offscreen native check cannot verify hardware video decoding or HDMI output.

The implementation uses [QTimer](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QTimer.html)
to revisit the current [local datetime](https://docs.python.org/3/library/datetime.html#datetime.datetime.now),
instead of sleeping until a previously computed future timestamp.
