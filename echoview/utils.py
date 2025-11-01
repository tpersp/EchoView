#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import subprocess
import requests
import random
import psutil
import shutil
from datetime import datetime

from echoview.config import (
    APP_VERSION,
    VIEWER_HOME,
    IMAGE_DIR,
    CONFIG_PATH,
    LOG_PATH,
    WEB_BG,
)

def init_config():
    if not os.path.exists(CONFIG_PATH):
        default_cfg = {
            "theme": "dark",
            # displays dictionary for multi-display logic
            "displays": {
                "Display0": {
                    "mode": "random_image",
                    "fallback_mode": "random_image",   # <-- New fallback mode default
                    "image_interval": 60,
                    "image_category": "",
                    "specific_image": "",
                    "shuffle_mode": False,
                    "mixed_folders": [],
                    "rotate": 0,
                    "web_url": "",
                    "spotify_info_position": "bottom-center",
                    "spotify_show_progress": False,
                    "spotify_progress_position": "bottom-center",   # New: progress bar location setting
                    "spotify_progress_theme": "dark",         # New: progress bar theme option
                    "spotify_progress_update_interval": 200,       # New: update interval in ms
                    "spotify_font_color": "#FFFFFF",
                    "video_category": "",
                    "shuffle_videos": False,
                    "video_mute": True,
                    "video_volume": 100,
                    "video_play_to_end": True,
                    "video_max_seconds": 120
                }
            },
            "overlay": {
                "overlay_enabled": True,       # Changed from False so overlay is always on
                "clock_enabled": False,        # Off by default
                "background_enabled": False,   # Off by default
                "font_color": "#FFFFFF",
                "bg_color": "#000000",
                "bg_opacity": 0.4,
                "offset_x": 20,
                "offset_y": 20,
                "overlay_width": 300,
                "overlay_height": 150,
                "clock_font_size": 26,
                "clock_position": "top-center",
                "layout_style": "stacked",
                "padding_x": 8,
                "padding_y": 6,
                "monitor_selection": "All"
            },
            "gui": {
                "background_blur_radius": 20,
                "background_scale_percent": 100,
                "foreground_scale_percent": 100
            },
            "cache_capacity": 15,
            "preload_count": 1,
            # Persist a list of websites visited in web page mode.  When a
            # new URL is entered for a display it will be appended here.  The
            # UI uses a datalist to offer these as suggestions, making it
            # easier to switch back to previously viewed pages.
            "saved_websites": [],
            "spotify": {
                "client_id": "",
                "client_secret": "",
                "redirect_uri": "",
                "scope": "user-read-currently-playing user-read-playback-state"
            }
        }
        save_config(default_cfg)
    try:
        with open(CONFIG_PATH, "r") as f:
            cfg = json.load(f)
    except Exception:
        return

    if "displays" in cfg and len(cfg["displays"]) > 1:
        removed = False
        for key in list(cfg["displays"].keys()):
            if key.lower() in ("display0", "default"):
                del cfg["displays"][key]
                removed = True
        if removed:
            save_config(cfg)

def load_config():
    if not os.path.exists(CONFIG_PATH):
        init_config()
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

def log_message(msg):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(f"{datetime.now()}: {msg}\n")
    print(msg)

def get_system_stats():
    cpu = psutil.cpu_percent(interval=0.4)
    mem = psutil.virtual_memory()
    mem_used_mb = (mem.total - mem.available) / (1024 * 1024)
    mem_total_mb = mem.total / (1024 * 1024)
    load1 = 0
    try:
        load1 = os.getloadavg()[0]
    except:
        pass
    temp = "N/A"
    try:
        out = subprocess.check_output(["vcgencmd", "measure_temp"]).decode().strip()
        temp = out
    except:
        pass
    return (cpu, mem_used_mb, mem_total_mb, load1, temp)

def get_storage_stats(path=IMAGE_DIR):
    """Return used and total bytes for the given path."""
    try:
        usage = shutil.disk_usage(path)
        return usage.used, usage.total
    except Exception:
        return 0, 0

def format_bytes(num_bytes):
    """Return human readable string like 1.2GB given bytes."""
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024.0:
            return f"{size:.1f}{unit}"
        size /= 1024.0
    return f"{size:.1f}PB"

def get_hostname():
    try:
        return subprocess.check_output(["hostname"]).decode().strip()
    except:
        return "UnknownHost"

def get_ip_address():
    try:
        out = subprocess.check_output(["hostname", "-I"]).decode().strip()
        ips = out.split()
        for ip in ips:
            if not ip.startswith("127."):
                return ip
        return "Unknown"
    except:
        return "Unknown"

def get_pi_model():
    path = "/proc/device-tree/model"
    if os.path.exists(path):
        with open(path, "r") as f:
            return f.read().strip()
    return "Unknown Model"

def get_subfolders():
    """Return a sorted list of subfolders inside IMAGE_DIR."""
    try:
        folders = [
            d for d in os.listdir(IMAGE_DIR)
            if os.path.isdir(os.path.join(IMAGE_DIR, d))
        ]
        folders.sort(key=lambda x: x.lower())
        return folders
    except Exception:
        return []

def count_files_in_folder(folder_path):
    if not os.path.isdir(folder_path):
        return 0
    cnt = 0
    valid_ext = (
        ".png", ".jpg", ".jpeg", ".gif",
        ".mp4", ".mov", ".avi", ".mkv", ".webm"
    )
    for f in os.listdir(folder_path):
        if f.lower().endswith(valid_ext):
            cnt += 1
    return cnt

