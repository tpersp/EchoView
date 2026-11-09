"""Validated presentation policy and geometry, independent of Qt or hardware."""
import math

EDGES = ("left", "right", "top", "bottom")
DEFAULT_SAFE_AREA = dict.fromkeys(EDGES, 0.0)
RESOURCE_PROFILES = ("standard", "pi3")


def bounded_int(value, default, minimum, maximum):
    try:
        return max(minimum, min(maximum, int(value)))
    except (ValueError, TypeError, OverflowError):
        return default


def safe_area_settings(values, strict=False):
    if not isinstance(values, dict):
        if strict:
            raise ValueError("Safe area must specify margins for each edge.")
        values = {}
    margins = {}
    for edge in EDGES:
        try:
            value = float(values.get(edge, 0))
            if not math.isfinite(value) or not 0 <= value <= 20:
                raise ValueError
        except (ValueError, TypeError):
            if strict:
                raise ValueError("Each safe-area margin must be a finite percentage from 0 to 20.") from None
            value = 0.0
        margins[edge] = value
    return margins


def safe_bounds(width, height, margins):
    margins = safe_area_settings(margins)
    left = round(width * margins["left"] / 100)
    right = round(width * margins["right"] / 100)
    top = round(height * margins["top"] / 100)
    bottom = round(height * margins["bottom"] / 100)
    return left, top, max(1, width - left - right), max(1, height - top - bottom)


def overlay_bounds(container, size, position, margin=10, y_offset=0):
    x, y, width, height = container
    margin = max(0, min(margin, width // 4, height // 4))
    label_w = max(1, min(size[0], width - 2 * margin))
    label_h = max(1, min(size[1], height - 2 * margin))
    dx = margin if "left" in position else (width - label_w - margin if "right" in position else (width - label_w) // 2)
    dy = margin + y_offset if "top" in position else (height - label_h - margin - y_offset if "bottom" in position else (height - label_h) // 2)
    return x + dx, y + max(margin, min(height - margin - label_h, dy)), label_w, label_h


def text_stretch(pixel_aspect):
    return max(1, min(4000, round(100 / pixel_aspect))) if pixel_aspect > 0 else 100


def resource_settings(profile, cfg):
    gui = cfg.get("gui", {})
    low = profile == "pi3"
    return {
        "blur_radius": 0 if low else bounded_int(gui.get("background_blur_radius", 0), 0, 0, 100),
        "cache_capacity": min(4 if low else 100, bounded_int(cfg.get("cache_capacity", 15), 15, 0, 100)),
        "cache_budget": (32 if low else 128) * 1024 * 1024,
        "decode_pixels": 1280 * 720 if low else 16 * 1024 * 1024,
        "decode_side": 1920 if low else 8192,
        "preload_count": 0 if low else bounded_int(cfg.get("preload_count", 1), 1, 0, 2),
        "animate_gifs": not low,
        "progress_interval": 500 if low else 50,
        "max_stream_height": 480 if low else None,
    }


def decode_size(width, height, policy):
    if width <= 0 or height <= 0:
        return 0, 0
    factor = min(1.0, math.sqrt(policy["decode_pixels"] / (width * height)), policy["decode_side"] / max(width, height))
    return max(1, int(width * factor)), max(1, int(height * factor))


def trim_image_cache(cache, capacity, budget):
    total = sum(value.get("bytes", 0) for value in cache.values())
    while cache and (len(cache) > capacity or total > budget):
        _, value = cache.popitem(last=False)
        total -= value.get("bytes", 0)
    return total


def player_presentation_flags(display):
    flags = []
    for edge, value in safe_area_settings(display.get("safe_area", {})).items():
        if value:
            flags.append(f"--video-margin-ratio-{edge}={value / 100:g}")
    if display.get("resource_profile") == "pi3":
        flags += ["--vd-lavc-threads=2", "--ytdl-format=bestvideo[height<=480]+bestaudio/best[height<=480]"]
    return flags


def runtime_display_settings(cfg, display):
    """Combine screen preferences with the device policy without persisting a copy."""
    return {**display, "resource_profile": cfg.get("resource_profile", "standard")}
