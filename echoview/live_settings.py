"""Small local request/ack channel for Spotify visual changes on the Qt thread."""
import json
import os
from pathlib import Path
import secrets
import tempfile
import time

from echoview.web.spotify_auth import fingerprint

VISUAL_KEYS = frozenset({
    'spotify_layout', 'spotify_font_size', 'spotify_info_position', 'spotify_font_color',
    'spotify_show_song', 'spotify_show_artist', 'spotify_show_album', 'spotify_show_device',
    'spotify_negative_font', 'spotify_show_progress', 'spotify_progress_position',
    'spotify_progress_theme', 'spotify_smooth_progress', 'spotify_progress_update_interval',
})


def visual_changes(previous, current):
    """Return affected displays only when every change can be made in place."""
    if {k:v for k,v in previous.items() if k != 'displays'} != {k:v for k,v in current.items() if k != 'displays'}:
        return []
    before, after = previous.get('displays', {}), current.get('displays', {})
    if before.keys() != after.keys():
        return []
    changed = []
    for name, values in after.items():
        old = before[name]
        if old == values:
            continue
        if old.get('mode') != 'spotify' or values.get('mode') != 'spotify':
            return []
        if {k:v for k,v in old.items() if k not in VISUAL_KEYS} != {k:v for k,v in values.items() if k not in VISUAL_KEYS}:
            return []
        changed.append(name)
    return changed


def atomic_json(directory, name, value):
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, path = tempfile.mkstemp(dir=directory, prefix='.visual-')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream)
        os.replace(path, directory/name)
    finally:
        Path(path).unlink(missing_ok=True)


def request_update(directory, cfg, displays, timeout=3):
    revision = secrets.token_hex(16)
    atomic_json(directory, 'visual-request.json', dict(revision=revision, config=fingerprint(cfg),
                displays=displays, expires=time.time()+15))
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        try:
            ack = json.loads((Path(directory)/'visual-ack.json').read_text())
            if isinstance(ack, dict) and ack.get('revision') == revision:
                return ack.get('applied') is True
        except (OSError, ValueError):
            pass
        time.sleep(.05)
    return False


class VisualSettingsReceiver:
    """Poll cheap local metadata. Invoke apply_request only for a new request."""
    def __init__(self, directory, apply_request):
        self.directory, self.apply_request = Path(directory), apply_request
        self.stamp = None
        self.revision = None

    def poll(self):
        try:
            path = self.directory/'visual-request.json'
            stat = path.stat()
            stamp = (stat.st_ino, stat.st_mtime_ns)
            if stamp == self.stamp:
                return
            self.stamp = stamp
            request = json.loads(path.read_text())
            revision = request['revision']
            if revision == self.revision:
                return
            self.revision = revision
            try:
                applied = request['expires'] >= time.time() and bool(self.apply_request(request))
            except (OSError, RuntimeError, ValueError, KeyError, TypeError):
                applied = False
            atomic_json(self.directory, 'visual-ack.json', dict(revision=revision, applied=applied))
        except (OSError, ValueError, KeyError, TypeError):
            pass  # A missing or malformed request never affects playback.
