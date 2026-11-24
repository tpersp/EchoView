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

- NAS service offline or share unusable: confirm after a two-second retry.
- If the service responds but the share still fails, request one ordinary restart
  of only that mount unit and recheck after two seconds. Busy mounts may refuse
  this; no forced/lazy unmounts or viewer stops are used. Existing jobs are left alone.
- Still unavailable/unusable: request a guarded reboot in the **same watchdog run**.
  An offline NAS also gets one reboot attempt, then the continuous-outage guard
  prevents repeated reboots until the share becomes healthy.

There is no 15-minute share grace or sequence of attempts across multiple timer
runs. The existing roughly five-minute detection interval is unchanged.

An isolated transient systemd probe has an four-second runtime limit. Its fixed
unit name prevents accumulating stuck filesystem probes; completed/failed units
are collected. A stuck kernel filesystem task cannot block the watchdog itself.
Local media configurations skip the NAS checks.

## Reboot guards and storage

There is a 60-second boot settling guard, but no multi-minute failure grace or
hours-long block on a new recovered-then-failed connection. Only one reboot is
allowed per continuous network/share failure episode. That latch survives reboot
and is shared across failure types so a single outage cannot trigger separate
network and storage reboot loops.

Protection re-arms after healthy share/connectivity checks at least five minutes
apart. This healthy confirmation occurs **after recovery**, not before the first
reboot. A new failure can then be handled promptly, without waiting six hours.
The reboot decision is recorded durably before the request. A backwards clock
change suppresses rather than bypasses protection; boot changes discard incomplete
healthy-confirmation windows. Missing/corrupt recovery machinery fails closed and
never falls back to an unguarded reboot.

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
