# Updating and reconnecting

Choose and save the update branch in Settings before updating. Installing a
checkout from `dev` does not itself change the saved update preference.

An update backs up configuration, fetches the selected branch, installs runtime
dependencies and restarts the viewer. The controller restart (or full-update
reboot) is scheduled through a systemd timer five seconds later so the browser
can receive the maintenance response. The page waits ten seconds, then checks
for the controller every three seconds and returns to Settings, where the
installed version is visible. A manual return link remains available.

This fixes a reproduced Pi issue: immediately queuing a controller restart with
`systemctl --no-block` stopped the request worker before it could deliver the
update response, leaving the browser showing a connection error even though
installation had completed. systemd-run creates an independent timer rather
than a child sleep process that would be terminated with the controller.
See [systemd-run timer options](https://www.freedesktop.org/software/systemd/man/latest/systemd-run.html).

Update errors name the failing stage. Installer output is streamed to
`VIEWER_HOME/.update-backups/before-*/installer.log`, with owner-only access;
the error page gives the exact path. Read this log over SSH, not through a
public download route. Avoid sharing it without checking for private details.
Backups include the previous revision, configuration and token cache. Failed
installation does not automatically roll back code or dependencies; inspect the
reported stage before retrying.

For a connection error, check whether the controller returned and which
version is running:

```bash
systemctl status controller.service echoview.service --no-pager -l
journalctl -u controller.service --since '15 minutes ago' --no-pager
```

When the version remains unchanged, also verify that the intended commit was
pushed to the selected remote branch. Reinstalling the same revision can
succeed without changing the displayed version.
