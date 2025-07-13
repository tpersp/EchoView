# EchoView

EchoView is a lightweight, cross-device visual display system for Linux-based devices (e.g., Raspberry Pi). It supports multiple monitors, each running a customizable slideshow or display mode (images, GIFs, videos, Spotify album art, etc.).

## Features
- Multi-monitor support
- Customizable slideshows and display modes
- Overlays: time, weather (OpenWeather API), custom text
- Web-based controller (FastAPI backend + simple frontend)
- Media uploads
- Spotify and weather API integration
- Systemd integration for service management
- Per-monitor settings
- Remote sub-device management

## Tech Stack
- Python 3.x
- PySide6 (GUI)
- FastAPI (web controller)

## Getting Started
1. Install Python 3.x and pip.
2. Install dependencies:
   ```sh
   pip install -r requirements.txt
   ```
3. Run the FastAPI server:
   ```sh
   uvicorn web.main:app --reload
   ```
4. Run the PySide6 display app:
   ```sh
   python display/main.py
   ```

## Project Structure
- `web/` - FastAPI backend and frontend
- `display/` - PySide6 GUI application
- `systemd/` - Example service files
- `.github/` - Copilot instructions

## Notes
- Ensure all API keys and secrets are set in your environment or config files before deploying. No placeholders remain in the codebase.
- For systemd integration, see `systemd/README.md`.
