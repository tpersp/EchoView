# Optional network and NAS recovery

Enable the watchdog during installation and choose a primary host/IP (for example,
the NAS) and an optional fallback (for example, the gateway). Each round pings the
primary first, then the fallback only if necessary. A response from either resets
the network failure counter. Defaults remain five rounds per run and a threshold
of three consecutive failed rounds, within a run. The timer runs about every five
minutes with its existing scheduling jitter.

## Network recovery

When both targets repeatedly fail, the watchdog first checks whether the configured
NAS service is reachable despite failed pings. If it is, network reconnection is
skipped. Otherwise it can reconnect an existing active physical NetworkManager
profile, without changing saved network settings. Targets are checked again before
requesting a guarded reboot. Reconnect attempts are at least 15 minutes apart.

## NAS share recovery

For a CIFS/NFS media mount declared in `/etc/fstab`, the watchdog checks the NAS
service (TCP 445/2049) and then whether the share's top-level directory can be read
as the viewer user. It does not recursively scan or open media files, change
credentials, write to the NAS, or restart the NAS itself. An empty local directory
under a missing mount is not accepted as a healthy share.

- NAS service offline: wait and retry; no share recovery reboot.
- Service responds but share unusable: allow 15 minutes for normal reconnection.
- Still unusable: request an ordinary restart of only that mount unit, with up to
  three attempts separated by at least five minutes. Busy mounts may refuse this;
  no forced/lazy unmounts or viewer stops are used. Existing mount jobs are left alone.
- Still unusable on a later check: request a guarded reboot as a last resort.

An isolated transient systemd probe has an eight-second runtime limit. Its fixed
unit name prevents accumulating stuck filesystem probes; completed/failed units
are collected. A stuck kernel filesystem task cannot block the watchdog itself.
Local media configurations skip the NAS checks.

## Reboot guards and storage

There is a 15-minute boot grace and a six-hour minimum between automatic reboots.
Only one reboot is allowed per continuous network/share failure episode. That
latch survives reboot and clears only when the relevant connectivity/share becomes
healthy, preventing reboot loops during a persistent outage. The cooldown is
recorded durably before requesting reboot; a backwards clock change suppresses,
rather than bypasses, it. Missing/corrupt recovery machinery never falls back to
an unguarded reboot.

State is kept in one bounded (4 KiB) private JSON file plus an empty lock file under
`.network-watchdog-recovery`, outside the NAS. Logs use the existing bounded
`viewer.log`; no per-check report files accumulate. Ordinary systemd lifecycle
messages remain subject to OS journal retention.

## Configuration and updates

`network-watchdog.conf` retains the existing fields:

```sh
WATCHDOG_TARGET=nas.example
WATCHDOG_FALLBACK_TARGET=192.168.1.1
WATCHDOG_ATTEMPTS=5
WATCHDOG_FAIL_THRESHOLD=3
```

An empty fallback retains single-target network checking. Media-root discovery uses
`IMAGE_DIR` from the application environment/`.env` and the declared network mount,
without probing media paths to discover mounts. Updates preserve targets/thresholds;
a disabled watchdog stays disabled. Invalid targets skip the reboot decision and
write an error instead of treating malformed configuration as network failure.

The probe uses [systemd-run](https://freedesktop.org/software/systemd/man/latest/systemd-run.html)
for isolated timeout handling. Mount recovery respects the existing
[systemd.mount](https://www.freedesktop.org/software/systemd/man/255/systemd.mount.html)
force/lazy flags and skips units configured to use those behaviors.
