#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import secrets
import subprocess
import requests
from flask import (
    Blueprint, request, redirect, url_for, render_template,
    send_from_directory, send_file, jsonify, session, current_app, flash
)
from echoview.config import (
    APP_VERSION,
    WEB_BG,
    IMAGE_DIR,
    LOG_PATH,
    UPDATE_BRANCH,
    VIEWER_HOME,
    SPOTIFY_CACHE_PATH,
)
from echoview.utils import (
    load_config, save_config, init_config, log_message,
    get_system_stats, get_subfolders, count_files_in_folder,
    get_hostname, get_ip_address, get_pi_model,
    get_storage_stats, format_bytes,
    CONFIG_PATH,
    is_ignored_folder,
    media_aspect_label,
)
from echoview.web.spotify_auth import DEFAULT_SCOPE, validate_config, cached_status, oauth_client
from echoview.presentation import safe_area_settings, RESOURCE_PROFILES, EDGES
from echoview.displays import (discover_monitors, reconcile_displays, mode_choices,
                               apply_output_mode, DISPLAY_ASPECTS)
from echoview import embed_utils

# Supported media file extensions for the upload/file-manager features.
VALID_MEDIA_EXT = (
    ".jpg", ".jpeg", ".png", ".gif",
    ".mp4", ".mov", ".avi", ".mkv", ".webm"
)

def detect_monitors_extended():
    return discover_monitors()


def get_local_monitors_from_config(cfg):
    # A saved preference is not evidence that a hardware mode was applied.
    inventory = discover_monitors()
    return {name: {"resolution": inventory.get(name, {}).get("current_mode") or "?"}
            for name in cfg.get("displays", {})}

def compute_overlay_preview(overlay_cfg, monitors_dict):
    """
    Used for overlay preview, only.
    This new version ignores manual sizing settings (removed) and
    computes a preview overlay box automatically.
    """
    selection = overlay_cfg.get("monitor_selection", "All")
    if selection == "All":
        maxw, maxh = 0, 0
        for dname, minfo in monitors_dict.items():
            try:
                w_str, h_str = minfo["resolution"].split("x")
                w, h = int(w_str), int(h_str)
                if w > maxw:
                    maxw = w
                if h > maxh:
                    maxh = h
            except:
                pass
        if maxw == 0 or maxh == 0:
            total_w, total_h = 1920, 1080
        else:
            total_w, total_h = maxw, maxh
    else:
        if selection in monitors_dict:
            try:
                part = monitors_dict[selection]["resolution"]
                w_str, h_str = part.split("x")
                total_w, total_h = int(w_str), int(h_str)
            except:
                total_w, total_h = 1920, 1080
        else:
            total_w, total_h = 1920, 1080

    max_preview_w = 400
    if total_w > 0:
        scale_factor = float(max_preview_w) / float(total_w)
    else:
        scale_factor = 0.2
    preview_width = int(total_w * scale_factor)
    preview_height = int(total_h * scale_factor)

    # Auto-compute overlay preview box as a fixed proportion of preview size
    overlay_box_width = int(preview_width * 0.3)
    overlay_box_height = int(preview_height * 0.2)
    overlay_box_left = int(preview_width * 0.05)
    overlay_box_top = int(preview_height * 0.05)
    preview_overlay = {
         "width": overlay_box_width,
         "height": overlay_box_height,
         "left": overlay_box_left,
         "top": overlay_box_top,
    }
    return (preview_width, preview_height, preview_overlay)

main_bp = Blueprint("main", __name__, static_folder="static")

@main_bp.route("/stats")
def stats_json():
    cpu, mem_used_mb, mem_total_mb, load1, temp = get_system_stats()
    used_bytes, total_bytes = get_storage_stats()
    used_human = format_bytes(used_bytes)
    total_human = format_bytes(total_bytes)
    return jsonify({
        "cpu_percent": cpu,
        "mem_used_mb": round(mem_used_mb, 1),
        "mem_total_mb": round(mem_total_mb, 1),
        "load_1min": round(load1, 2),
        "temp": temp,
        "disk_used": used_human,
        "disk_total": total_human
    })

@main_bp.route("/list_monitors")
def list_monitors():
    return jsonify({name: {**monitor, "resolution": monitor["current_mode"],
                           "offset_x": monitor["x"], "offset_y": monitor["y"],
                           "available_modes": mode_choices(monitor)}
                    for name, monitor in discover_monitors().items()})

@main_bp.route("/list_folders")
def list_folders():
    return jsonify(get_subfolders())


@main_bp.route("/player/youtube")
def youtube_player():
    cfg = load_config()
    display = cfg.get("displays", {}).get(request.args.get("display", ""))
    if not display:
        return "Unknown display.", 404
    previous = embed_utils.deserialize_embed_metadata(display.get("embed_metadata"))
    metadata = embed_utils.classify_url(display.get("web_url") or (previous.original_url if previous else ""))
    if metadata.embed_type != "youtube" or not (metadata.video_id or metadata.playlist_id or metadata.channel_id):
        return "A video, playlist or channel ID is needed for embedding. Select the external browser for channel handles.", 400
    origin = request.url_root.rstrip("/")
    embed_url = embed_utils.playback_embed_url(metadata, display, origin)
    return render_template("youtube_player.html", embed_url=embed_url)


@main_bp.route("/streaming/status")
def streaming_status():
    from echoview.streaming import capabilities
    return jsonify(capabilities())


@main_bp.route("/embed/refresh", methods=["POST"])
def refresh_embed():
    payload = request.get_json(silent=True) or {}
    display = payload.get("display")
    url = (payload.get("url") or "").strip()
    cfg = load_config()

    if not display:
        return jsonify({"ok": False, "error": "missing_display"}), 400
    displays = cfg.get("displays", {})
    if display not in displays:
        return jsonify({"ok": False, "error": "unknown_display"}), 404

    metadata = None
    if url:
        try:
            metadata = embed_utils.classify_url(url, enrich=True)
        except Exception as exc:  # pragma: no cover - defensive logging
            log_message(f"Embed classification failed for {url}: {exc}")
            return jsonify({"ok": False, "error": "classification_failed"}), 500

    display_cfg = displays[display]
    display_cfg["web_url"] = url
    display_cfg["embed_metadata"] = embed_utils.serialize_embed_metadata(metadata)

    if url and cfg.get("saved_websites"):
        enriched = None
        if metadata:
            enriched = {
                "url": url,
                "title": metadata.title,
                "provider": metadata.provider,
                "embed_type": metadata.embed_type,
                "metadata": embed_utils.serialize_embed_metadata(metadata),
            }
        for idx, entry in enumerate(cfg["saved_websites"]):
            if (entry == url) or (isinstance(entry, dict) and entry.get("url") == url):
                cfg["saved_websites"][idx] = enriched if enriched else url
                break

    save_config(cfg)

    response = {
        "ok": True,
        "embed_type": metadata.embed_type if metadata else "iframe",
        "metadata": display_cfg["embed_metadata"],
        "options": {
            "youtube_autoplay": display_cfg.get("youtube_autoplay", True),
            "youtube_mute": display_cfg.get("youtube_mute", True),
            "youtube_captions": display_cfg.get("youtube_captions", False),
            "youtube_quality": display_cfg.get("youtube_quality", "default"),
        },
    }
    return jsonify(response)

@main_bp.route("/images/<path:filename>")
def serve_image(filename):
    return send_from_directory(IMAGE_DIR, filename)

@main_bp.route("/thumb/<path:filename>")
def serve_thumbnail(filename):
    """Return a small JPEG thumbnail for the requested image."""
    size = request.args.get("size", "200")
    try:
        size = int(size)
    except Exception:
        size = 200
    src_path = os.path.join(IMAGE_DIR, filename)
    if not os.path.exists(src_path):
        return "", 404
    thumb_dir = os.path.join(VIEWER_HOME, ".thumbcache")
    os.makedirs(thumb_dir, exist_ok=True)
    safe_name = filename.replace("/", "_")
    thumb_path = os.path.join(thumb_dir, f"{safe_name}_{size}.jpg")
    if (not os.path.exists(thumb_path) or
            os.path.getmtime(thumb_path) < os.path.getmtime(src_path)):
        from PIL import Image
        try:
            im = Image.open(src_path)
            im.thumbnail((size, size))
            im.convert("RGB").save(thumb_path, "JPEG")
        except Exception:
            return send_from_directory(IMAGE_DIR, filename)
    return send_file(thumb_path, mimetype="image/jpeg")

@main_bp.route("/bg_image")
def bg_image():
    if os.path.exists(WEB_BG):
        return send_file(WEB_BG)
    return "", 404

@main_bp.route("/download_log")
def download_log():
    if os.path.exists(LOG_PATH):
        return send_file(LOG_PATH, as_attachment=True)
    return "No log file found", 404

@main_bp.route("/download/<path:filename>")
def download_file(filename):
    """Download a media file."""
    full_path = os.path.join(IMAGE_DIR, filename)
    if os.path.exists(full_path):
        return send_file(full_path, as_attachment=True)
    return "", 404

@main_bp.route("/move_image", methods=["POST"])
def move_image():
    rel_path = request.form.get("path", "")
    dest = request.form.get("dest", "")
    src = os.path.join(IMAGE_DIR, rel_path)
    dest_dir = os.path.join(IMAGE_DIR, dest)
    if os.path.isfile(src) and os.path.isdir(dest_dir):
        dst = os.path.join(dest_dir, os.path.basename(src))
        os.rename(src, dst)
    return redirect(url_for("main.upload_media"))

@main_bp.route("/upload_media", methods=["GET", "POST"])
def upload_media():
    cfg = load_config()
    theme = cfg.get("theme", "dark")
    if request.method == "GET":
        sort_opt = request.args.get("sort", "name_asc")
        folder_files = {}
        subfolders = get_subfolders()
        for sf in subfolders:
            try:
                folder_path = os.path.join(IMAGE_DIR, sf)
                files = [
                    f for f in os.listdir(folder_path)
                    if f.lower().endswith(VALID_MEDIA_EXT)
                ]
                if sort_opt.startswith("name"):
                    files.sort(reverse=(sort_opt == "name_desc"))
                else:
                    files.sort(
                        key=lambda x: os.path.getmtime(os.path.join(folder_path, x)),
                        reverse=(sort_opt == "date_desc")
                    )
                folder_files[sf] = files
            except Exception:
                folder_files[sf] = []
        return render_template(
            "upload_media.html",
            theme=theme,
            folder_files=folder_files,
            sort_option=sort_opt,
            subfolders=subfolders,
        )

    files = request.files.getlist("mediafiles")
    if not files:
        return "No files selected", 400

    subfolder = request.form.get("subfolder", "")

    target_dir = os.path.join(IMAGE_DIR, subfolder)
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

    for f in files:
        if not f.filename:
            continue
        lf = f.filename.lower()
        if not lf.endswith(VALID_MEDIA_EXT):
            log_message(f"Unsupported file type: {f.filename}")
            continue
        final_path = os.path.join(target_dir, f.filename)
        f.save(final_path)
        log_message(f"Uploaded file: {final_path}")

    return redirect(url_for("main.upload_media"))

@main_bp.route("/restart_viewer", methods=["POST"])
def restart_viewer():
    try:
        subprocess.check_output(["sudo", "systemctl", "restart", "echoview.service"])
        return redirect(url_for("main.index"))
    except subprocess.CalledProcessError as e:
        return f"Failed to restart service: {e}", 500

@main_bp.route("/restart_device", methods=["POST"])
def restart_device():
    try:
        subprocess.check_output(["sudo", "reboot"])
        return redirect(url_for("main.index"))
    except subprocess.CalledProcessError as e:
        return f"Failed to restart device: {e}", 500

@main_bp.route("/power_off", methods=["POST"])
def power_off():
    try:
        subprocess.check_output(["sudo", "poweroff"])
        return "Device is powering off...", 200
    except subprocess.CalledProcessError as e:
        return f"Failed to power off: {e}", 500

@main_bp.route("/delete_image", methods=["POST"])
def delete_image():
    rel_path = request.form.get("path", "")
    full = os.path.join(IMAGE_DIR, rel_path)
    if os.path.exists(full):
        os.remove(full)
    return redirect(url_for("main.upload_media"))

@main_bp.route("/rename_image", methods=["POST"])
def rename_image():
    rel_path = request.form.get("path", "")
    new_name = request.form.get("new_name", "")
    if not rel_path or not new_name:
        return redirect(url_for("main.upload_media"))
    full = os.path.join(IMAGE_DIR, rel_path)
    new_full = os.path.join(os.path.dirname(full), new_name)
    if os.path.exists(full):
        os.rename(full, new_full)
    return redirect(url_for("main.upload_media"))

@main_bp.route("/delete_folder", methods=["POST"])
def delete_folder():
    folder = request.form.get("folder", "")
    full = os.path.join(IMAGE_DIR, folder)
    if os.path.isdir(full):
        try:
            for f in os.listdir(full):
                os.remove(os.path.join(full, f))
            os.rmdir(full)
        except Exception:
            pass
    return redirect(url_for("main.upload_media"))

@main_bp.route("/rename_folder", methods=["POST"])
def rename_folder():
    folder = request.form.get("folder", "")
    new_name = request.form.get("new_name", "")
    if folder and new_name:
        src = os.path.join(IMAGE_DIR, folder)
        dst = os.path.join(IMAGE_DIR, new_name)
        if os.path.isdir(src):
            os.rename(src, dst)
    return redirect(url_for("main.upload_media"))

@main_bp.route("/create_folder", methods=["POST"])
def create_folder():
    name = request.form.get("folder_name", "").strip()
    if name:
        path = os.path.join(IMAGE_DIR, name)
        os.makedirs(path, exist_ok=True)
    return redirect(url_for("main.upload_media"))

@main_bp.route("/settings", methods=["GET", "POST"])
def settings():
    cfg = load_config()
    if request.method == "POST":
        new_theme = request.form.get("theme", "dark")
        cfg["theme"] = new_theme

        if new_theme == "custom":
            if "bg_image" in request.files:
                f = request.files["bg_image"]
                if f and f.filename:
                    f.save(WEB_BG)


        if "gui" not in cfg:
            cfg["gui"] = {}
        try:
            cfg["gui"]["background_blur_radius"] = int(request.form.get("background_blur_radius", "20"))
        except:
            cfg["gui"]["background_blur_radius"] = 20

        try:
            cfg["gui"]["background_scale_percent"] = int(request.form.get("background_scale_percent", "100"))
        except:
            cfg["gui"]["background_scale_percent"] = 100

        try:
            cfg["gui"]["foreground_scale_percent"] = int(request.form.get("foreground_scale_percent", "100"))
        except:
            cfg["gui"]["foreground_scale_percent"] = 100

        try:
            cfg["cache_capacity"] = int(request.form.get("cache_capacity", cfg.get("cache_capacity", 15)))
        except:
            cfg["cache_capacity"] = cfg.get("cache_capacity", 15)
        try:
            cfg["preload_count"] = int(request.form.get("preload_count", cfg.get("preload_count", 1)))
        except:
            cfg["preload_count"] = cfg.get("preload_count", 1)
        if cfg["preload_count"] < 0:
            cfg["preload_count"] = 0

        save_config(cfg)
        return redirect(url_for("main.settings"))

    else:
        cfg = load_config()
        theme = cfg.get("theme", "dark")
        return render_template(
            "settings.html",
            theme=theme,
            cfg=cfg,
            update_branch=UPDATE_BRANCH,
            version=APP_VERSION
        )

@main_bp.route('/toggle_theme', methods=['POST'])
def toggle_theme():
    """Quickly switch between dark and light themes and redirect back."""
    cfg = load_config()
    current = cfg.get('theme', 'dark')
    cfg['theme'] = 'light' if current == 'dark' else 'dark'
    save_config(cfg)
    return redirect(request.form.get('return_to') or url_for('main.index'))

@main_bp.route("/clear_config", methods=["POST"])
def clear_config():
    """
    Wipes the viewerconfig.json and resets it to defaults.
    Then restarts echoview.
    """
    if os.path.exists(CONFIG_PATH):
        os.remove(CONFIG_PATH)
        log_message("viewerconfig.json has been deleted. Re-initializing config.")
    init_config()  # recreate default config
    try:
        subprocess.check_call(["sudo", "systemctl", "restart", "echoview.service"])
    except subprocess.CalledProcessError as e:
        log_message(f"Failed to restart echoview.service after clearing config: {e}")
    return redirect(url_for("main.settings"))

@main_bp.route("/configure_spotify", methods=["GET", "POST"])
def configure_spotify():
    cfg = load_config()
    cfg.setdefault("spotify", {})
    if request.method == "POST":
        new = {key: request.form.get(key, "").strip()
               for key in ("client_id", "client_secret", "redirect_uri")}
        new["scope"] = request.form.get("scope", DEFAULT_SCOPE).strip()
        try:
            validate_config(new)
        except ValueError as exc:
            return str(exc), 400
        if new != cfg["spotify"]:
            # Invalidate before saving: never use another application's cached token.
            try:
                os.unlink(SPOTIFY_CACHE_PATH)
            except FileNotFoundError:
                pass
            except OSError:
                return "Cannot invalidate old Spotify token; check cache permissions.", 500
            session.pop("spotify_browser", None)
        cfg["spotify"] = new
        save_config(cfg)
        return redirect(url_for("main.configure_spotify"))
    return render_template("configure_spotify.html", spotify=cfg["spotify"],
                           theme=cfg.get("theme", "dark"),
                           spotify_status=cached_status(cfg["spotify"], SPOTIFY_CACHE_PATH))


@main_bp.route("/spotify_auth")
def spotify_auth():
    cfg = load_config().get("spotify", {})
    try:
        auth = oauth_client(cfg, SPOTIFY_CACHE_PATH)
        browser = secrets.token_urlsafe(32)
        session["spotify_browser"] = browser
        state = current_app.extensions["spotify_states"].issue(browser, cfg)
        return redirect(auth.get_authorize_url(state=state))
    except ValueError as exc:
        return str(exc), 400
    except Exception:
        return "Could not start Spotify authorization. Check installation and cache permissions.", 503


@main_bp.route("/callback")
def callback():
    cfg = load_config().get("spotify", {})
    state = request.args.get("state", "")
    browser = session.pop("spotify_browser", None)
    if not state or not browser or not current_app.extensions["spotify_states"].consume(state, browser, cfg):
        return "Authorization expired or state did not match. Start authorization again in the same browser and address.", 400
    if request.args.get("error"):
        return "Spotify authorization was declined. You can authorize again.", 400
    code = request.args.get("code")
    if not code:
        return "Authorization failed: no code provided.", 400
    try:
        token = oauth_client(cfg, SPOTIFY_CACHE_PATH).get_access_token(code, check_cache=False)
        if not isinstance(token, dict) or not token.get("access_token"):
            return "Spotify did not return a valid token. Authorize again.", 502
        if not set(cfg.get("scope", DEFAULT_SCOPE).split()).issubset(str(token.get("scope", "")).split()):
            try:
                os.unlink(SPOTIFY_CACHE_PATH)
            except FileNotFoundError:
                pass
            return "Spotify did not grant the required permissions. Authorize again.", 400
    except Exception:
        # Provider exceptions may contain authorization codes or credentials.
        return "Spotify token exchange failed. Check credentials, registered redirect URI and network, then authorize again.", 502
    return redirect(url_for("main.configure_spotify"))


@main_bp.route("/spotify_check", methods=["POST"])
def spotify_check():
    cfg = load_config().get("spotify", {})
    try:
        auth = oauth_client(cfg, SPOTIFY_CACHE_PATH)
        token = auth.get_cached_token()  # Spotipy validates scopes and refreshes expired tokens.
        if not token:
            return "No usable Spotify token. Authorize again.", 400
        import spotipy
        spotipy.Spotify(auth=token["access_token"], requests_timeout=5,
                        retries=0, status_retries=0).current_playback()
        return "Spotify connection verified. No active playback is also a valid result."
    except Exception as exc:
        status = getattr(exc, "http_status", None)
        if status == 401:
            return "Spotify token rejected. Authorize again.", 401
        if status == 403:
            return "Spotify access denied. Check scopes, Developer Dashboard allowed users and app-owner Premium status.", 403
        if status == 429:
            return "Spotify rate or quota limit reached. Wait before checking again.", 429
        return "Spotify connection or refresh failed. Check network and credentials; reauthorize if access was revoked.", 503

@main_bp.route("/overlay_config", methods=["GET", "POST"])
def overlay_config():
    cfg = load_config()
    if request.method == "POST":
        sizes = {}
        for monitor in cfg.get("displays", {}):
            try:
                sizes[monitor] = int(request.form.get(f"{monitor}_clock_font_size", "26"))
            except (ValueError, TypeError):
                return "Clock font size must be an integer from 8 to 512.", 400
            if not 8 <= sizes[monitor] <= 512:
                return "Clock font size must be an integer from 8 to 512.", 400
        for monitor in cfg.get("displays", {}):
            new_overlay = {
                "clock_enabled": (f"{monitor}_clock_enabled" in request.form),
                "clock_font_size": sizes[monitor],
                "font_color": request.form.get(f"{monitor}_font_color", "#FFFFFF"),
                "auto_negative_font": (f"{monitor}_auto_negative_font" in request.form),
                "clock_position": request.form.get(f"{monitor}_clock_position", "bottom-center"),
            }
            if "displays" in cfg and monitor in cfg["displays"]:
                cfg["displays"][monitor]["overlay"] = new_overlay
        if "overlay" not in cfg:
            cfg["overlay"] = {}
        try:
            cfg["overlay"]["offset_x"] = int(request.form.get("offset_x", "0"))
            cfg["overlay"]["offset_y"] = int(request.form.get("offset_y", "0"))
        except Exception:
            pass
        save_config(cfg)
        try:
            subprocess.check_call(["sudo", "systemctl", "restart", "echoview.service"])
        except subprocess.CalledProcessError as e:
            log_message(f"Failed to restart echoview.service: {e}")
        return redirect(url_for("main.overlay_config"))
    else:
        monitors_cfg = cfg.get("displays", {})
        return render_template(
            "overlay.html",
            theme=cfg.get("theme", "dark"),
            monitors=monitors_cfg,
        )

@main_bp.route("/display/presentation", methods=["POST"])
def configure_presentation():
    cfg = load_config()
    name = request.form.get("display", "")
    if name not in cfg.get("displays", {}):
        return "Unknown display.", 400
    display = cfg["displays"][name]
    profile = request.form.get("resource_profile", display.get("resource_profile", "standard"))
    if profile not in RESOURCE_PROFILES:
        return "Invalid resource profile.", 400
    old = safe_area_settings(display.get("safe_area", {}))
    try:
        margins = safe_area_settings({edge: request.form.get("safe_" + edge, old.get(edge, 0)) for edge in EDGES}, strict=True)
    except ValueError as exc:
        return str(exc), 400
    display.update(safe_area=margins, resource_profile=profile)
    save_config(cfg)
    try:
        subprocess.run(["sudo", "systemctl", "restart", "echoview.service"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        flash("Safe area and resource settings saved.")
    except (OSError, subprocess.SubprocessError):
        flash("Presentation settings saved; restart the viewer to apply them.")
    return redirect(url_for("main.index"))


@main_bp.route("/display/output", methods=["POST"])
def configure_output():
    cfg = load_config()
    name = request.form.get("display", "")
    if name not in cfg.get("displays", {}):
        return "Unknown display.", 400
    selection = request.form.get("output_mode", "auto")
    aspect = request.form.get("display_aspect", "auto")
    if aspect not in DISPLAY_ASPECTS:
        return "Invalid physical display aspect ratio.", 400
    try:
        apply_output_mode(name, selection)
    except ValueError as exc:
        return str(exc), 400
    except RuntimeError as exc:
        return str(exc), 503
    cfg["displays"][name]["output_mode"] = selection
    cfg["displays"][name]["display_aspect"] = aspect
    save_config(cfg)
    try:
        subprocess.run(["sudo", "systemctl", "restart", "echoview.service"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        flash("Display mode applied and settings saved.")
    except (OSError, subprocess.SubprocessError):
        flash("Display mode applied and settings saved; restart the viewer to use the new aspect setting.")
    return redirect(url_for("main.index"))


@main_bp.route("/", methods=["GET", "POST"])
def index():
    cfg = load_config()

    # Re-detect extended monitors, just to show their current resolution
    ext_mons = detect_monitors_extended()
    if "displays" not in cfg:
        cfg["displays"] = {}

    if reconcile_displays(cfg, ext_mons):
        save_config(cfg)

    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "update_displays":
            # Update display modes, categories, etc.
            for dname in cfg["displays"]:
                pre = dname + "_"
                dcfg = cfg["displays"][dname]
                new_mode = request.form.get(pre + "mode", dcfg["mode"])
                new_interval_s = request.form.get(pre + "image_interval", str(dcfg["image_interval"]))
                new_cat = request.form.get(pre + "image_category", dcfg["image_category"])
                if is_ignored_folder(new_cat):
                    new_cat = ""
                aspect_filter = request.form.get(pre + "aspect_filter", dcfg.get("aspect_filter", "any"))
                if aspect_filter not in ("any", "square", "landscape", "portrait"):
                    aspect_filter = "any"
                shuffle_val = request.form.get(pre + "shuffle_mode", "no")
                new_spec = request.form.get(pre + "specific_image", dcfg["specific_image"])
                rotate_str = request.form.get(pre + "rotate", "0")
                mixed_str = request.form.get(pre + "mixed_order", "")
                mixed_list = [x for x in mixed_str.split(",") if x and not is_ignored_folder(x)]
                new_vid_cat = request.form.get(pre + "video_category", dcfg.get("video_category", ""))
                if is_ignored_folder(new_vid_cat):
                    new_vid_cat = ""
                shuffle_videos_val = request.form.get(pre + "shuffle_videos", "no")
                video_mute_val = request.form.get(pre + "video_mute")
                video_vol_str = request.form.get(pre + "video_volume", str(dcfg.get("video_volume", 100)))
                video_play_to_end_val = request.form.get(pre + "video_play_to_end")
                video_max_str = request.form.get(pre + "video_max_seconds", str(dcfg.get("video_max_seconds", 120)))

                try:
                    new_interval = int(new_interval_s)
                except:
                    new_interval = dcfg["image_interval"]
                try:
                    new_rotate = int(rotate_str)
                except:
                    new_rotate = 0

                old_url = dcfg.get("web_url", "").strip()
                new_url = request.form.get(pre + "web_url", dcfg.get("web_url", ""))

                dcfg["mode"] = new_mode
                dcfg["image_interval"] = new_interval
                dcfg["image_category"] = new_cat
                dcfg["shuffle_mode"] = (shuffle_val == "yes")
                dcfg["specific_image"] = new_spec
                dcfg["rotate"] = new_rotate
                dcfg["aspect_filter"] = aspect_filter
                dcfg["web_url"] = new_url
                dcfg["web_use_external_browser"] = True if request.form.get(pre + "web_use_external_browser") else False
                dcfg["youtube_autoplay"] = True if request.form.get(pre + "youtube_autoplay") else False
                dcfg["youtube_mute"] = True if request.form.get(pre + "youtube_mute") else False
                dcfg["youtube_captions"] = True if request.form.get(pre + "youtube_captions") else False
                dcfg["youtube_quality"] = request.form.get(pre + "youtube_quality", dcfg.get("youtube_quality", "default")) or "default"

                url_stripped = new_url.strip()
                metadata_obj = None
                needs_refresh = url_stripped != old_url or not dcfg.get("embed_metadata")
                if needs_refresh:
                    if url_stripped:
                        try:
                            metadata_obj = embed_utils.classify_url(url_stripped)
                        except Exception as exc:  # pragma: no cover
                            log_message(f"Embed classification failed during save for {url_stripped}: {exc}")
                            metadata_obj = None
                    dcfg["embed_metadata"] = embed_utils.serialize_embed_metadata(metadata_obj)
                else:
                    metadata_obj = embed_utils.deserialize_embed_metadata(dcfg.get("embed_metadata"))

                if request.form.get(pre + "save_web"):
                    cfg.setdefault("saved_websites", [])
                    if url_stripped:
                        existing_entries = cfg["saved_websites"]
                        already_present = any(
                            (entry == url_stripped)
                            or (isinstance(entry, dict) and entry.get("url") == url_stripped)
                            for entry in existing_entries
                        )
                        if not already_present:
                            entry = {"url": url_stripped}
                            if metadata_obj:
                                entry.update({
                                    "title": metadata_obj.title,
                                    "provider": metadata_obj.provider,
                                    "embed_type": metadata_obj.embed_type,
                                    "metadata": embed_utils.serialize_embed_metadata(metadata_obj),
                                })
                            existing_entries.append(entry if entry.get("metadata") else url_stripped)

                # If Spotify, store extras
                if new_mode == "spotify":
                    dcfg["fallback_mode"] = request.form.get(pre + "fallback_mode", dcfg.get("fallback_mode", "random_image"))
                    dcfg["spotify_show_song"] = True if request.form.get(pre + "spotify_show_song") else False
                    dcfg["spotify_show_artist"] = True if request.form.get(pre + "spotify_show_artist") else False
                    dcfg["spotify_show_album"] = True if request.form.get(pre + "spotify_show_album") else False
                    try:
                        dcfg["spotify_font_size"] = int(request.form.get(pre + "spotify_font_size", "18"))
                    except:
                        dcfg["spotify_font_size"] = 18
                    dcfg["spotify_negative_font"] = True if request.form.get(pre + "spotify_negative_font") else False
                    dcfg["spotify_font_color"] = request.form.get(pre + "spotify_font_color", dcfg.get("spotify_font_color", "#FFFFFF"))
                    dcfg["spotify_info_position"] = request.form.get(pre + "spotify_info_position", dcfg.get("spotify_info_position", "bottom-center"))
                    # New: store the live progress bar option and its settings
                    dcfg["spotify_show_progress"] = True if request.form.get(pre + "spotify_show_progress") else False
                    dcfg["spotify_progress_position"] = request.form.get(pre + "spotify_progress_position", dcfg.get("spotify_progress_position", "below_info"))
                    dcfg["spotify_progress_theme"] = request.form.get(pre + "spotify_progress_theme", dcfg.get("spotify_progress_theme", "default"))
                    try:
                        dcfg["spotify_progress_update_interval"] = int(request.form.get(pre + "spotify_progress_update_interval", dcfg.get("spotify_progress_update_interval", 200)))
                    except:
                        dcfg["spotify_progress_update_interval"] = 200

                if new_mode == "mixed":
                    dcfg["mixed_folders"] = mixed_list
                else:
                    dcfg["mixed_folders"] = []
                if new_mode == "videos":
                    dcfg["video_category"] = new_vid_cat
                    dcfg["shuffle_videos"] = (shuffle_videos_val == "yes")
                    dcfg["video_mute"] = True if video_mute_val else False
                    try:
                        dcfg["video_volume"] = int(video_vol_str)
                    except:
                        dcfg["video_volume"] = dcfg.get("video_volume", 100)
                    dcfg["video_play_to_end"] = True if video_play_to_end_val else False
                    try:
                        dcfg["video_max_seconds"] = int(video_max_str)
                    except:
                        dcfg["video_max_seconds"] = dcfg.get("video_max_seconds", 120)
                else:
                    dcfg["video_category"] = ""

            save_config(cfg)
            try:
                subprocess.check_call(["sudo", "systemctl", "restart", "echoview.service"])
            except:
                pass
            return redirect(url_for("main.index"))

    # Build folder counts
    folder_counts = {}
    for sf in get_subfolders():
        folder_counts[sf] = count_files_in_folder(os.path.join(IMAGE_DIR, sf))

    # Collect images for "specific_image" selection
    display_images = {}
    for dname, dcfg in cfg["displays"].items():
        cat = dcfg.get("image_category", "")
        base_dir = os.path.join(IMAGE_DIR, cat) if cat else IMAGE_DIR
        img_list = []
        if os.path.isdir(base_dir):
            for fname in os.listdir(base_dir):
                lf = fname.lower()
                if lf.endswith((".jpg", ".jpeg", ".png", ".gif")):
                    rel_path = fname
                    img_list.append(os.path.join(cat, rel_path) if cat else rel_path)
        img_list.sort()
        aspect_pref = dcfg.get("aspect_filter", "any")
        if aspect_pref not in ("", None, "any"):
            filtered = []
            for rel_path in img_list:
                full_path = os.path.join(IMAGE_DIR, rel_path)
                if not os.path.exists(full_path):
                    continue
                try:
                    label = media_aspect_label(full_path)
                except Exception:
                    label = "unknown"
                if label == aspect_pref:
                    filtered.append(rel_path)
            img_list = filtered
        display_images[dname] = img_list

    cpu, mem_used_mb, mem_total_mb, load1, temp = get_system_stats()
    used_bytes, total_bytes = get_storage_stats()
    disk_line = f"{format_bytes(used_bytes)}/{format_bytes(total_bytes)}"
    mem_line = f"{round(mem_used_mb, 1)}/{round(mem_total_mb, 1)}"
    host = get_hostname()
    ipaddr = get_ip_address()
    model = get_pi_model()
    theme = cfg.get("theme", "dark")

    sub_info_line = ""

    spotify_status = cached_status(cfg.get("spotify", {}), SPOTIFY_CACHE_PATH)

    final_monitors = {}
    for name in cfg["displays"]:
        monitor = ext_mons.get(name, {})
        final_monitors[name] = {
            "resolution": monitor.get("current_mode") or "Unknown",
            "refresh": monitor.get("current_rate"),
            "connected": monitor.get("connected", False), "active": monitor.get("active", False),
            "available_modes": mode_choices(monitor), "model_name": monitor.get("model") or "Unknown",
            "kind": monitor.get("kind", "unknown"),
        }

    return render_template(
        "index.html",
        cfg=cfg,
        subfolders=get_subfolders(),
        folder_counts=folder_counts,
        display_images=display_images,
        cpu=cpu,
        mem_line=mem_line,
        load1=round(load1, 2),
        temp=temp,
        disk_usage=disk_line,
        host=host,
        ipaddr=ipaddr,
        model=model,
        theme=theme,
        version=APP_VERSION,
        sub_info_line=sub_info_line,
        monitors=final_monitors,
        display_aspects=DISPLAY_ASPECTS,
        spotify_status=spotify_status
    )


def _update_response(reboot=False):
    from echoview.updates import update, UpdateError
    try:
        update(VIEWER_HOME, UPDATE_BRANCH, CONFIG_PATH, SPOTIFY_CACHE_PATH, reboot=reboot)
    except UpdateError as exc:
        log_message(str(exc))
        return render_template("maintenance.html", message=str(exc), pending=False), 500
    message = ("Installation completed. Reboot requested; wait for the device to return."
               if reboot else "Installation completed and viewer is active. Controller restart queued.")
    return render_template("maintenance.html", message=message, pending=True), 202


@main_bp.route("/update_app", methods=["POST"])
def update_app():
    return _update_response()


@main_bp.route("/full_update", methods=["POST"])
def full_update():
    return _update_response(reboot=True)


@main_bp.route("/restart_services", methods=["POST"])
def restart_services():
    from echoview.updates import restart_services as restart, UpdateError
    try:
        restart()
    except UpdateError as exc:
        return render_template("maintenance.html", message=str(exc), pending=False), 500
    return render_template("maintenance.html", message="Viewer is active. Controller restart queued.", pending=True), 202
