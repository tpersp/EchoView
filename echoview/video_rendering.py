"""Lightweight mpv resizing on Raspberry Pi; no source-media inspection."""
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def scaling_flags():
    """Detect hardware once; retain mpv defaults on other/unknown devices."""
    try:
        model = Path('/proc/device-tree/model').read_text().rstrip('\x00\n')
    except (OSError, UnicodeError):
        return ()
    if not model.startswith('Raspberry Pi'):
        return ()
    # Avoid costly multi-pass convolution scaling on the shared Pi GPU.
    return ('--scale=bilinear', '--cscale=bilinear', '--dscale=bilinear')


def frame_rate_flags():
    """Apply the 24 fps ceiling on Pi, bypassing the filter for native <=24 fps."""
    if not scaling_flags():
        return ()
    return ('--script=' + str(Path(__file__).with_name('video_fps_limit.lua')),)
