# AGENTS.md

## Purpose

This file documents the agents, services, and automated components that interact with or manage the EchoView application. It is intended to help developers, maintainers, and users understand the roles and responsibilities of each agent in the system.

## What is an Agent?

An "agent" in EchoView refers to any automated process, service, or script that performs tasks on behalf of the user or system. Agents can be systemd services, background scripts, web controllers, or external integrations (such as Spotify or remote device management).

## EchoView Agents Overview

### 1. Display Agent
- **File:** `echoview.py`
- **Role:** Manages slideshow windows, overlays, and display logic for each connected monitor.
- **Type:** Systemd service (`echoview.service`)

### 2. Web Controller Agent
- **File:** `app.py` (and related web modules)
- **Role:** Provides the FastAPI/Flask web interface for configuration, device management, uploads, and remote control.
- **Type:** Systemd service (`controller.service`)

### 3. Setup Agent
- **File:** `setup.sh`
- **Role:** Automates installation, configuration, and system integration (systemd, Openbox, Picom, etc.).
- **Type:** Shell script (run manually or via automation)

### 4. Network Watchdog Agent (Optional)
- **Role:** Monitors network connectivity and reboots the device if offline.
- **Type:** Cron job (configured during setup)

### 5. Remote Device Agents
- **Role:** Sub-devices managed by the main EchoView instance, which can push/pull display configs and perform remote configuration.
- **Type:** Managed via web controller and device manager

### 6. Spotify Integration Agent
- **Role:** Fetches and displays currently playing track info and album art.
- **Type:** Integrated in display agent (`echoview.py`)

## Adding New Agents

To add a new agent, create a dedicated script, service, or module, and document its purpose, entry point, and integration steps here.

## Maintenance

- Keep this file updated as new agents or services are added.
- Ensure all agents are documented with their role, entry point, and configuration details.

---

For questions or contributions, see the main `README.md` or open an issue in the repository.
