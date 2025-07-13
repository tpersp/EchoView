# Systemd Integration for EchoView

This folder contains example systemd service files for running EchoView components as services on Linux.

## Services
- `echoview-display.service`: Runs the PySide6 display app
- `echoview-web.service`: Runs the FastAPI web controller

## Usage
1. Edit the `ExecStart` and `WorkingDirectory` paths to match your installation.
2. Copy the service files to `/etc/systemd/system/`:
   ```sh
   sudo cp echoview-*.service /etc/systemd/system/
   ```
3. Reload systemd:
   ```sh
   sudo systemctl daemon-reload
   ```
4. Enable and start the services:
   ```sh
   sudo systemctl enable echoview-display.service
   sudo systemctl start echoview-display.service
   sudo systemctl enable echoview-web.service
   sudo systemctl start echoview-web.service
   ```
