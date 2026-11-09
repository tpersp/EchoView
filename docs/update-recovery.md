# Updates and recovery

Both update buttons fetch the configured origin branch and run setup in
`--auto-update` mode, including dependency/constraint verification even when only
requirements changed. Update restarts services; Full Update requests a reboot.
The checkout stays on its existing branch. Application updates do not change the
selected boot profile, OS version or X11/Wayland session.

Before resetting code, the updater refuses local tracked changes and configuration
files tracked by either current or target Git revision. Save development work
separately before updating. Ignored/untracked media and configuration are kept;
there is no `git clean`. Concurrent updates are refused using a process lock.

Each attempt saves existing `.env`, viewer configuration (including Spotify client
settings, connector/mode/aspect and safe areas), and the configured Spotify token
cache under `.update-backups/before-*` in the checkout. Directories are private
(0700) and copied files are 0600. The previous Git revision is recorded there.
These backups contain credentials: keep them private and remove old backups
manually when no longer needed. Media and the virtualenv are not backed up.
Boot-profile backups remain separate; see [composite recovery](composite-video.md).

Failures stop subsequent stages. An installer failure never triggers a reboot
or planned service restart. The response identifies the failed stage without
printing captured command output or credentials. Changes to packages, code or
services already made by setup are not automatically rolled back. A request
interrupted by a network/proxy timeout has an unknown outcome: inspect the device
before retrying. The web request can take up to 30 minutes for setup.

On Update, viewer restart is checked and the controller restart is queued without
waiting for the controller to terminate its own worker. HTTP 202 means the request
was accepted; it does not prove the controller returned or a reboot completed.
Reconnect manually after the device is ready. Restart Services is POST-only.
The service user needs noninteractive sudo access to the existing setup/systemctl
operations; denied permissions produce an error instead of prompting indefinitely.

## Inspect and recover on the device

Use an SSH session or local terminal, replacing checkout and backup paths:

```bash
cd /path/to/EchoView
sudo systemctl status echoview.service controller.service
sudo journalctl -u echoview.service -u controller.service -n 100 --no-pager
cat .update-backups/before-EXAMPLE/previous-revision
```

Inspect journals locally before sharing them. After fixing the reported issue,
rerun `sudo bash setup.sh --auto-update` from the correct checkout, then restart
services and check their status. Keep the existing `.env`; an absent configuration
is an error rather than a reason to generate fresh settings during an update.
Restore individual saved configuration files to their original locations only
if they were damaged, preserving ownership and restrictive token permissions.

If old code must be restored, first save any new local changes, inspect the saved
revision and check out that revision deliberately. Reinstall its matching runtime
requirements before restarting. Dependency/OS changes are not undone by restoring
Git files alone; a disk-image backup remains the full rollback mechanism.

## Graphical startup

Viewer startup waits for an authenticated `xrandr --query` on its configured
DISPLAY/XAUTHORITY instead of sleeping for five seconds. It waits up to 60 seconds
(default), then fails with an actionable journal message and systemd retries.
`ECHOVIEW_DISPLAY_WAIT_SECONDS` accepts 1–120. Setup uses the configured display
and authority or the viewer user's actual account home, including non-pi users.
Readiness confirms X access, not correct HDMI/RCA timing or actual rendering.

Mocked update/install/restart failures, private backups, settings preservation,
concurrency and readiness timeout tests pass without invoking real updates or
systemd. Fresh/upgrade Pi installation, cold boot and recovery tests remain pending.

## Select the update branch

In **Settings → Update from GitHub**, choose a branch and click **Save update
branch** before running either update action. The saved choice overrides the
legacy `UPDATE_BRANCH` environment setting; that setting remains the fallback
until a branch has been saved. Saving never fetches application code or starts
an installation. Both update actions use the saved selection.

The dropdown initially uses local `origin` refs, the saved branch, and main/dev
fallbacks. An asynchronous read-only `git ls-remote --heads origin` lookup loads
available remote branches without delaying the settings page. GitHub is queried
when it is the checkout's origin; no GitHub account connection is required. Results
are cached for 60 seconds, network lookup is limited to eight seconds, and offline
failures preserve the existing choices. Branch names use letters, digits, underscores,
dots, hyphens and slashes with Git ref restrictions; revision expressions and
option-like input are rejected. Updates explicitly fetch the selected branch,
including for checkouts originally cloned with a single-branch refspec. A branch
deleted upstream remains selected but the update fails at fetch rather than
silently switching to another branch.

[Git remote branch discovery](https://git-scm.com/docs/git-ls-remote) and
[ref-name rules](https://git-scm.com/docs/git-check-ref-format) describe the
underlying Git operations.
