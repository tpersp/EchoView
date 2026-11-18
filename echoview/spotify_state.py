"""A private local snapshot shared by the viewer and read-only controller UI."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time

from echoview.web.spotify_auth import fingerprint

STALE_SECONDS = 45


def state_directory(home):
    identity = hashlib.sha256(os.path.abspath(home).encode()).hexdigest()[:12]
    # Linux shared memory avoids periodic SD-card writes on the Pi.
    base = Path('/dev/shm')
    if not base.is_dir() or not os.access(base, os.W_OK):
        base = Path(tempfile.gettempdir())
    return base / f'echoview-spotify-{os.getuid()}-{identity}'


class StatePublisher:
    def __init__(self, directory, clock=time.time, monotonic=time.monotonic):
        self.directory = Path(directory)
        self.clock, self.monotonic = clock, monotonic
        self.art_key = None
        self.art_url = None

    def __call__(self, result, cfg):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        now = self.clock()
        key = None
        if result.art_url and result.art_path:
            key = hashlib.sha256(result.art_url.encode()).hexdigest()[:16]
            target = self.directory / f'art-{key}.jpg'
            if not target.exists():
                from PIL import Image
                with Image.open(result.art_path) as image:
                    image = image.convert('RGB')
                    image.thumbnail((320, 320))
                    self._atomic(target, lambda stream: image.save(stream, format='JPEG', quality=85))
            self.art_key, self.art_url = key, result.art_url
        elif result.art_url == self.art_url:
            key = self.art_key
        # Explicit allowlist: never serialize the API payload, credentials or tokens.
        state = {name: getattr(result, name) for name in
                 ('status', 'song', 'artist', 'album', 'progress_ms', 'duration_ms',
                  'device_name', 'device_type', 'shuffle', 'repeat')}
        state.update(published_at=now, sampled_at=now-max(0, self.monotonic()-result.fetched_time),
                     account=fingerprint(cfg), artwork=key)
        self._atomic(self.directory / 'state.json', lambda stream: stream.write(json.dumps(state).encode()))
        # Keep a bounded pair of artwork thumbnails; never touch source media.
        images = sorted(self.directory.glob('art-*.jpg'), key=lambda path: path.stat().st_mtime, reverse=True)
        keep = {self.directory / f'art-{key}.jpg'} if key else set()
        for image in images:
            if image in keep:
                continue
            if len(keep) < 2:
                keep.add(image)
            else:
                image.unlink(missing_ok=True)

    def _atomic(self, target, write):
        fd, name = tempfile.mkstemp(dir=self.directory, prefix='.snapshot-')
        try:
            with os.fdopen(fd, 'wb') as stream:
                write(stream)
            os.replace(name, target)
        finally:
            Path(name).unlink(missing_ok=True)


def read_state(directory, cfg, active, now=None):
    if not active:
        return {'status': 'inactive'}
    now = time.time() if now is None else now
    try:
        with (Path(directory) / 'state.json').open() as source:
            state = json.load(source)
        if state.pop('account', None) != fingerprint(cfg):
            return {'status': 'waiting'}
        age = max(0, now - float(state.pop('published_at')))
        sampled_at = float(state.pop('sampled_at'))
        if age > STALE_SECONDS:
            return {'status': 'stale'}
        if state['status'] == 'playing':
            state['progress_ms'] = min(state['duration_ms'], state['progress_ms'] + max(0, now-sampled_at)*1000)
        return state
    except (OSError, ValueError, TypeError, KeyError):
        return {'status': 'waiting'}
