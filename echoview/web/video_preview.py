"""On-demand video contact sheets: one low-priority worker, bounded local cache."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

MAX_BYTES = 20 * 1024 * 1024
MAX_FILES = 128
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='video-preview')
_lock = threading.Lock()
_pending = set()
_failures = {}


def _run(args, timeout):
    prefix = ['nice', '-n', '15'] if shutil.which('nice') else []
    return subprocess.run(prefix + args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, timeout=timeout, check=True).stdout


def render(source, target, animated):
    """Seek to at most four frames; never write to or transcode the source."""
    duration = 0
    try:
        data = json.loads(_run(['ffprobe', '-v', 'error', '-threads', '1', '-protocol_whitelist', 'file,pipe',
                               '-show_entries', 'format=duration', '-of', 'json', str(source)], 4))
        duration = float(data.get('format', {}).get('duration', 0))
        if not 0 < duration < 1e9:duration = 0
    except (ValueError, TypeError, subprocess.SubprocessError):pass
    fractions = (.1, .35, .6, .85) if animated else (.1,)
    sheet = Image.new('RGB', (256 * len(fractions), 144), 'black')
    for index, fraction in enumerate(fractions):
        data = _run(['ffmpeg', '-nostdin', '-v', 'error', '-threads', '1',
                     '-filter_threads', '1', '-protocol_whitelist', 'file,pipe',
                     '-ss', str(duration * fraction), '-i', str(source), '-an', '-sn', '-dn',
                     '-frames:v', '1', '-vf',
                     'scale=256:144:force_original_aspect_ratio=decrease,pad=256:144:(ow-iw)/2:(oh-ih)/2',
                     '-threads', '1', '-f', 'image2pipe', '-vcodec', 'mjpeg', '-'], 8)
        with Image.open(io.BytesIO(data)) as frame:sheet.paste(frame.convert('RGB'), (256 * index, 0))
    # Atomic replacement means clients never receive a partial JPEG.
    temporary = target.with_suffix('.tmp')
    try:
        sheet.save(temporary, 'JPEG', quality=75)
        temporary.chmod(0o600)
        os.replace(temporary, target)
    finally:temporary.unlink(missing_ok=True)


def trim(directory):
    for temporary in directory.glob('*.tmp'):temporary.unlink(missing_ok=True)
    files = sorted(directory.glob('*.jpg'), key=lambda path:path.stat().st_mtime, reverse=True)
    total = 0
    for index, path in enumerate(files):
        size = path.stat().st_size
        if index >= MAX_FILES or total + size > MAX_BYTES:path.unlink(missing_ok=True)
        else:total += size


def request_preview(source, directory, animated=False):
    """Return (ready path, HTTP status). No decoder work on request threads."""
    source = Path(source)
    info = source.stat()
    key = hashlib.sha256(f'{source}\0{info.st_mtime_ns}\0{info.st_size}\0{animated}'.encode(errors='surrogatepass')).hexdigest()
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = directory / (key + '.jpg')
    if target.is_file():return target, 200
    identity = str(target)
    with _lock:
        now = time.monotonic()
        if now - _failures.get(identity, float('-inf')) < 30:return None, 503
        if identity in _pending or len(_pending) >= 8:return None, 202
        _pending.add(identity)
    def generate():
        try:
            render(source, target, animated)
            trim(directory)
        except Exception:
            with _lock:
                if len(_failures) >= 128:_failures.pop(next(iter(_failures)))
                _failures[identity] = time.monotonic()
        finally:
            with _lock:_pending.discard(identity)
    try:_executor.submit(generate)
    except Exception:
        with _lock:_pending.discard(identity)
        return None, 503
    return None, 202
