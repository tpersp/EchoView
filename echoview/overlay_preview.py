"""On-demand, bounded viewer frames over private shared-memory files."""
import base64
import fcntl
from io import BytesIO
import json
import os
from pathlib import Path
import re
import secrets
import time

from echoview.live_settings import atomic_json

MAX_MESSAGE = 2 * 1024 * 1024


class PreviewUnavailable(Exception):
    pass


def _read(path, limit=MAX_MESSAGE):
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Preview message too large')
    return json.loads(data)


def request_frame(directory, display, timeout=2):
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(directory / 'lock', os.O_CREAT | os.O_RDWR, 0o600)
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise PreviewUnavailable('Preview busy') from None
                time.sleep(.025)
        revision = secrets.token_hex(16)
        atomic_json(directory, 'request.json', dict(revision=revision, display=display, expires=time.time()+3))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                response = _read(directory / 'response.json')
                if response.get('revision') == revision and response.get('display') == display:
                    if response.get('error'):
                        raise PreviewUnavailable('Preview unavailable')
                    image = base64.b64decode(response['jpeg'], validate=True)
                    if not image.startswith(b'\xff\xd8') or len(image) > MAX_MESSAGE:
                        raise ValueError('Invalid preview image')
                    return image
            except (OSError, ValueError, KeyError, TypeError):
                pass
            time.sleep(.025)
        raise PreviewUnavailable('Viewer unavailable')
    finally:
        os.close(fd)


class FrameReceiver:
    def __init__(self, directory, capture, submit):
        self.directory, self.capture, self.submit = Path(directory), capture, submit
        self.stamp = None
        self.last_capture = 0

    def _reply(self, response):
        try:
            atomic_json(self.directory, 'response.json', response)
        except OSError:
            pass  # Preview storage failures must never affect playback.

    def poll(self):
        try:
            path = self.directory / 'request.json'
            stat = path.stat()
            stamp = (stat.st_ino, stat.st_mtime_ns)
            if stamp == self.stamp:
                return
            # Bound GUI work even with multiple tabs/devices requesting frames.
            if time.monotonic() - self.last_capture < .5:
                return
            self.stamp = stamp
            request = _read(path, 8192)
            revision, display = request['revision'], request['display']
            if (not isinstance(revision, str) or not re.fullmatch(r'[0-9a-f]{32}', revision)
                    or not isinstance(display, str) or not 0 < len(display) <= 200
                    or not time.time() <= request['expires'] <= time.time()+5):
                return
        except (OSError, ValueError, TypeError, KeyError):
            return
        response = dict(revision=revision, display=display)
        self.last_capture = time.monotonic()
        try:
            width, height, rgba = self.capture(display)
            if not (0 < width <= 640 and 0 < height <= 640 and len(rgba) == width*height*4):
                raise ValueError('Invalid capture size')
        except Exception:
            self._reply(dict(response, error=True))
            return

        def encode():
            try:
                # Qt image plugins never run on this worker (codec/GIL lock order).
                from PIL import Image
                stream = BytesIO()
                Image.frombytes('RGBA', (width, height), rgba).convert('RGB').save(stream, format='JPEG', quality=88)
                response['jpeg'] = base64.b64encode(stream.getvalue()).decode('ascii')
            except Exception:
                response['error'] = True
            self._reply(response)

        if not self.submit(encode):
            self._reply(dict(response, error=True))
