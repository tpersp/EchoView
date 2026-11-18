"""Shared, serialized Spotify polling. No Qt objects or GUI work live here."""
from dataclasses import dataclass, replace
import hashlib
import math
from pathlib import Path
import tempfile
import threading
import time
from collections import OrderedDict

import requests

POLL_SECONDS = 5
MAX_ART_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class Playback:
    status: str
    song: str = ""
    artist: str = ""
    album: str = ""
    progress_ms: int = 0
    duration_ms: int = 0
    fetched_time: float = 0
    art_url: str = ""
    art_path: str = ""
    next_poll_at: float = 0
    track_id: str = ""
    device_name: str = ""
    device_type: str = ""
    shuffle: bool = False
    repeat: str = "off"


def number(value):
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def normalize_playback(current, now):
    if not isinstance(current, dict) or not isinstance(current.get("item"), dict):
        return Playback("unavailable", fetched_time=now)
    item = current["item"]
    kind = current.get("currently_playing_type") or item.get("type", "track")
    if kind not in ("track", "episode"):
        return Playback("unavailable", fetched_time=now)
    album = item.get("album") or {}
    show = item.get("show") or {}
    if not isinstance(album, dict):
        album = {}
    if not isinstance(show, dict):
        show = {}
    artists = item.get("artists") or []
    artist = ", ".join(str(a.get("name") or "") for a in artists if isinstance(a, dict)) if isinstance(artists, list) else ""
    images = (item.get("images") or show.get("images") or []) if kind == "episode" else (album.get("images") or [])
    urls = [img["url"] for img in images if isinstance(img, dict) and isinstance(img.get("url"), str)] if isinstance(images, list) else []
    device = current.get("device") or {}
    if not isinstance(device, dict):
        device = {}
    return Playback(
        "playing" if current.get("is_playing") else "paused",
        track_id=str(item.get("uri") or item.get("id") or ""),
        device_name=str(device.get("name") or ""), device_type=str(device.get("type") or ""),
        shuffle=bool(current.get("shuffle_state")), repeat=str(current.get("repeat_state") or "off"),
        song=str(item.get("name") or ""),
        artist=str(show.get("publisher") or show.get("name") or "") if kind == "episode" else artist,
        album=str(show.get("name") or "") if kind == "episode" else str(album.get("name") or ""),
        progress_ms=number(current.get("progress_ms")), duration_ms=number(item.get("duration_ms")),
        fetched_time=now, art_url=urls[0] if urls else "",
    )


def error_policy(exc, failures):
    status = getattr(exc, "http_status", None)
    if status == 401 or getattr(exc, "error", None) == "invalid_grant":
        return "authorization_required", 60
    if status == 403:
        return "access_denied", 60
    if status == 429:
        quota = "QUOTA_EXCEEDED" in str(getattr(exc, "msg", "")) or getattr(exc, "reason", None) == "QUOTA_EXCEEDED"
        headers = getattr(exc, "headers", None) or {}
        try:
            delay = float(next((value for key, value in headers.items() if key.lower() == "retry-after"), 0))
            if not math.isfinite(delay):
                delay = 0
        except (TypeError, ValueError):
            delay = 0
        # Never retry earlier than Retry-After; quotas get a longer minimum pause.
        return ("quota_exceeded" if quota else "rate_limited"), max(300 if quota else 30, delay)
    return "offline", min(60, 5 * (2 ** min(failures, 4)))


class SpotifyPoller:
    def __init__(self, config_loader, cache_path, clock=time.monotonic, client_factory=None, artwork_get=requests.get, publisher=None):
        self.config_loader = config_loader
        self.cache_path = cache_path
        self.clock = clock
        self.client_factory = client_factory or self._client
        self.artwork_get = artwork_get
        self.publisher = publisher
        self.lock = threading.Lock()
        self.key = None
        self.auth = None
        self.http = None
        self.result = Playback("unavailable")
        self.next_poll = 0
        self.end_check_key = None
        self.failures = 0
        self.art_dir = None
        self.art_cache = OrderedDict()
        self.art_retry = {}

    def _client(self, cfg):
        import spotipy
        from echoview.web.spotify_auth import oauth_client
        if self.auth is None:
            self.http = requests.Session()
            self.auth = oauth_client(cfg, self.cache_path, requests_session=self.http)
        # get_cached_token validates scopes and refreshes an expired token itself.
        token = self.auth.get_cached_token()
        if not token:
            return None
        return spotipy.Spotify(auth=token["access_token"], requests_session=self.http,
                               requests_timeout=5, retries=0, status_retries=0)

    def _artwork(self, url):
        if not url:
            return ""
        if url in self.art_cache:
            self.art_cache.move_to_end(url)
            return self.art_cache[url]
        if self.clock() < self.art_retry.get(url, 0):
            return ""
        if self.art_dir is None:
            self.art_dir = tempfile.TemporaryDirectory(prefix="echoview-spotify-")
        path = Path(self.art_dir.name) / (hashlib.sha256(url.encode()).hexdigest() + ".jpg")
        try:
            started = self.clock()
            with self.artwork_get(url, stream=True, timeout=(3, 5)) as response:
                response.raise_for_status()
                total = 0
                with path.open("wb") as target:
                    for chunk in response.iter_content(65536):
                        total += len(chunk)
                        if total > MAX_ART_BYTES or self.clock() - started > 15:
                            raise ValueError("Artwork limit exceeded")
                        target.write(chunk)
            from PIL import Image
            with Image.open(path) as image:
                if max(image.width, image.height) > 4096:
                    raise ValueError("Artwork dimensions exceeded")
                image.verify()
            self.art_cache[url] = str(path)
            while len(self.art_cache) > 8:
                _, old = self.art_cache.popitem(last=False)
                Path(old).unlink(missing_ok=True)
            self.art_retry.pop(url, None)
            return str(path)
        except Exception:
            path.unlink(missing_ok=True)
            self.art_retry[url] = self.clock() + 30
            # Bound failed-URL bookkeeping as well as successful artwork storage.
            while len(self.art_retry) > 8:
                self.art_retry.pop(next(iter(self.art_retry)))
            return ""

    def fetch(self):
        """Call on a worker. A single lock coalesces windows and token refreshes."""
        with self.lock:
            request_started = None
            cfg = {}
            try:
                cfg = self.config_loader().get("spotify", {})
                key = tuple(str(cfg.get(k) or "") for k in ("client_id", "client_secret", "redirect_uri", "scope", "auth_method"))
                if key != self.key:
                    self.key, self.auth = key, None
                    if self.http:
                        self.http.close()
                        self.http = None
                    self.next_poll = 0
                    self.end_check_key = None
                    self.failures = 0
                if self.clock() < self.next_poll:
                    return self.result
                if not all(cfg.get(k) for k in ("client_id", "redirect_uri")):
                    result = Playback("authorization_required")
                    delay = 60
                else:
                    client = self.client_factory(cfg)
                    if client is None:
                        result, delay = Playback("authorization_required"), 60
                    else:
                        request_started = self.clock()
                        result = normalize_playback(client.current_playback(additional_types="track,episode"), self.clock())
                        if result.status == "playing":
                            result = replace(result, art_path=self._artwork(result.art_url))
                        delay = POLL_SECONDS
                    self.failures = 0
            except Exception as exc:
                self.failures += 1
                status, delay = error_policy(exc, self.failures)
                result = Playback(status, fetched_time=self.clock())
            if request_started is not None and result.status in ("playing", "paused", "unavailable"):
                # Keep a start-to-start cadence: API/artwork latency must not add
                # another cooldown and make the viewer miss the next deadline.
                self.next_poll = request_started + POLL_SECONDS
                if result.status == "playing" and result.duration_ms > result.progress_ms:
                    remaining = (result.duration_ms - result.progress_ms) / 1000
                    track_key = (result.song, result.artist, result.album, result.duration_ms)
                    if remaining > POLL_SECONDS:
                        self.end_check_key = None
                    candidate = max(request_started + 2, result.fetched_time + remaining + 0.25)
                    # Only one early check per ending, even if Spotify keeps
                    # reporting the same stale position near the end.
                    if candidate < self.next_poll and self.end_check_key != track_key:
                        self.next_poll = candidate
                        self.end_check_key = track_key
            else:
                # Provider Retry-After and error backoff begin after the response.
                self.next_poll = self.clock() + delay
            self.result = replace(result, next_poll_at=self.next_poll)
            if self.publisher:
                try:
                    self.publisher(self.result, cfg)
                except (OSError, ValueError):
                    pass  # A web snapshot failure must not interrupt the display.
            return self.result

    def close(self):
        """Use after workers finish; TemporaryDirectory also cleans up on exit."""
        with self.lock:
            if self.http:
                self.http.close()
            if self.art_dir:
                self.art_dir.cleanup()
            self.art_cache.clear()


_shared = None
_shared_lock = threading.Lock()


def shared_poller():
    global _shared
    with _shared_lock:
        if _shared is None:
            from echoview.utils import load_config
            from echoview.config import SPOTIFY_CACHE_PATH
            from echoview.config import VIEWER_HOME
            from echoview.spotify_state import StatePublisher, state_directory
            _shared = SpotifyPoller(load_config, SPOTIFY_CACHE_PATH,
                                    publisher=StatePublisher(state_directory(VIEWER_HOME)))
        return _shared
