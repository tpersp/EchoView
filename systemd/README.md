# Systemd Integration for EchoViewer

This folder contains example systemd service files for running EchoViewer components as services on Linux.

## Services
- `echoviewer-display.service`: Runs the PySide6 display app
- `echoviewer-web.service`: Runs the FastAPI web controller

## Usage
1. Edit the `ExecStart` and `WorkingDirectory` paths to match your installation.
2. Copy the service files to `/etc/systemd/system/`:
   ```sh
   sudo cp echoviewer-*.service /etc/systemd/system/
   ```
3. Reload systemd:
   ```sh
   sudo systemctl daemon-reload
   ```
4. Enable and start the services:
   ```sh
   sudo systemctl enable echoviewer-display.service
   sudo systemctl start echoviewer-display.service
   sudo systemctl enable echoviewer-web.service
   sudo systemctl start echoviewer-web.service
   ```
