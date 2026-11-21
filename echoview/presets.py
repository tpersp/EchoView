"""Named playback setups, independent of device and physical output settings."""
from copy import deepcopy
from echoview.displays import match_connector

MAX_PRESETS = 20
PLAYBACK_KEYS = {
    'mode', 'schedule', 'fallback_mode', 'image_interval', 'image_category', 'specific_image',
    'shuffle_mode', 'mixed_folders', 'rotate', 'aspect_filter', 'web_url',
    'web_use_external_browser', 'embed_metadata', 'youtube_autoplay', 'youtube_mute',
    'youtube_captions', 'youtube_quality', 'video_category', 'specific_video',
    'shuffle_videos', 'video_mute', 'video_volume', 'video_play_to_end', 'video_max_seconds',
    'spotify_show_song', 'spotify_show_artist', 'spotify_show_album', 'spotify_show_device', 'spotify_font_size',
    'spotify_negative_font', 'spotify_font_color', 'spotify_info_position',
    'spotify_layout', 'spotify_show_progress', 'spotify_show_time', 'spotify_progress_position', 'spotify_progress_theme',
    'spotify_progress_update_interval', 'spotify_smooth_progress',
}


def valid_name(value):
    value = value.strip()
    if not value or len(value) > 48 or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError('Use a preset name of 1–48 characters.')
    return value


def snapshot(cfg):
    result = {}
    for name, display in cfg.get('displays', {}).items():
        settings = {key: deepcopy(value) for key, value in display.items() if key in PLAYBACK_KEYS}
        # A preset created before choosing an individual video must clear one
        # selected later, rather than accidentally keeping it on restoration.
        settings.setdefault('specific_video', '')
        settings.setdefault('schedule', [])
        result[name] = settings
    if not result:
        raise ValueError('Configure a display before saving a preset.')
    return {'format': 1, 'displays': result}


def restore(cfg, preset):
    if not isinstance(preset, dict) or preset.get('format') != 1 or not isinstance(preset.get('displays'), dict):
        raise ValueError('This preset cannot be read. Save a new preset from the current setup.')
    result = deepcopy(cfg)
    matched = 0
    for name, settings in preset['displays'].items():
        target = match_connector(name, result.get('displays', {}))
        if not target or not isinstance(settings, dict):
            continue
        result['displays'][target].update({key: deepcopy(value) for key, value in settings.items() if key in PLAYBACK_KEYS})
        if 'spotify_show_device' not in settings and result['displays'][target].get('spotify_show_device'):
            result['displays'][target]['spotify_show_device'] = False
        if 'spotify_show_time' not in settings and result['displays'][target].get('spotify_show_time'):
            result['displays'][target]['spotify_show_time'] = False
        matched += 1
    if not matched:
        raise ValueError('This preset has no matching configured displays.')
    return result
