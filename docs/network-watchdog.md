# Optional network watchdog

Enable the watchdog during installation and choose a primary host/IP (for example,
the NAS) and an optional fallback (for example, the gateway). The primary is pinged
first. A successful primary skips the fallback. If primary fails, the fallback is
pinged; success on either resets the failure counter. Only consecutive rounds in
which neither target responds can trigger a reboot.

The existing defaults remain five rounds per run and a threshold of three
consecutive failed rounds. This counter is within a run, not across timer runs.
The timer runs about every five minutes, with its existing scheduling jitter.

These are ICMP reachability checks. They do not validate an SMB/NFS share or
restart the NAS. In particular, an unreachable NAS with a responding gateway
intentionally does not cause a Pi reboot.

Settings live in `network-watchdog.conf`:

```sh
WATCHDOG_TARGET=nas.example
WATCHDOG_FALLBACK_TARGET=192.168.1.1
WATCHDOG_ATTEMPTS=5
WATCHDOG_FAIL_THRESHOLD=3
```

An empty fallback retains the original single-target behavior. Existing installs
keep their targets and thresholds during updates; no fallback is silently added.
A disabled watchdog stays disabled. Invalid targets skip the reboot decision and
write an error rather than treating malformed configuration as network failure.
Watchdog decisions use the same bounded `viewer.log` as the application.
