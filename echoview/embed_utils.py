#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Utilities for classifying external URLs (YouTube, HLS, generic web pages)
and for retrieving embed metadata that EchoView can persist alongside the
viewer configuration.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests

try:
    import yt_dlp  # type: ignore

    _YT_DLP_AVAILABLE = True
except Exception:  # pragma: no cover - availability depends on host image
    yt_dlp = None
    _YT_DLP_AVAILABLE = False

YOUTUBE_DOMAINS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "gaming.youtube.com",
    "youtu.be",
    "www.youtu.be",
}

OEMBED_ENDPOINT = "https://www.youtube.com/oembed"
OEMBED_CACHE_TTL = 60 * 60 * 24  # 24 hours
_oembed_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
logger = logging.getLogger(__name__)
_cache_lock = threading.Lock()


@dataclass
class EmbedMetadata:
    """Serializable container for embed metadata stored in configuration."""

    embed_type: str
    original_url: str
    canonical_url: str
    provider: Optional[str] = None
    title: Optional[str] = None
    content_type: Optional[str] = None
    video_id: Optional[str] = None
    playlist_id: Optional[str] = None
    channel_id: Optional[str] = None
    start_seconds: Optional[int] = None
    thumbnail_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        # Ensure we only persist keys with meaningful values.
        return {k: v for k, v in data.items() if v is not None}

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["EmbedMetadata"]:
        if not data:
            return None
        return cls(
            embed_type=data.get("embed_type", "iframe"),
            original_url=data.get("original_url", ""),
            canonical_url=data.get("canonical_url", data.get("original_url", "")),
            provider=data.get("provider"),
            title=data.get("title"),
            content_type=data.get("content_type"),
            video_id=data.get("video_id"),
            playlist_id=data.get("playlist_id"),
            channel_id=data.get("channel_id"),
            start_seconds=data.get("start_seconds"),
            thumbnail_url=data.get("thumbnail_url"),
        )


def _is_youtube_host(netloc: str) -> bool:
    host = netloc.lower()
    if host in YOUTUBE_DOMAINS:
        return True
    if host.endswith(".youtube.com"):
        return True
    if host.endswith(".youtu.be"):
        return True
    return False


_TIME_REGEX = re.compile(
    r"^(?:(?P<hours>\d+)h)?(?:(?P<minutes>\d+)m)?(?:(?P<seconds>\d+)s)?$"
)


def _parse_start_time(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    if value.isdigit():
        return int(value)
    match = _TIME_REGEX.match(value)
    if not match:
        return None
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    total = hours * 3600 + minutes * 60 + seconds
    return total if total > 0 else None


def _sanitize_youtube_id(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_\-]", "", value)


def parse_youtube_url_details(url: str) -> Dict[str, Any]:
    """
    Inspect a potentially-YouTube URL and extract video/playlist identifiers.
    Returns a dictionary with keys: is_youtube, video_id, playlist_id,
    playlist_index, start_seconds.
    """
    parsed = urlparse(url.strip())
    if not parsed.scheme:
        # Assume https scheme if missing
        parsed = parsed._replace(scheme="https")
    details: Dict[str, Any] = {
        "is_youtube": False,
        "video_id": None,
        "playlist_id": None,
        "playlist_index": None,
        "start_seconds": None,
        "channel_id": None,
    }
    if not parsed.netloc or not _is_youtube_host(parsed.netloc):
        return details

    details["is_youtube"] = True
    qs = parse_qs(parsed.query)
    path_parts = [p for p in parsed.path.split("/") if p]

    video_id = None
    playlist_id = None
    playlist_index = None

    if parsed.netloc.endswith("youtu.be") and path_parts:
        video_id = _sanitize_youtube_id(path_parts[0])
    elif "v" in qs:
        video_id = _sanitize_youtube_id(qs["v"][0])
    elif path_parts and path_parts[0] in {"embed", "shorts", "live"} and len(path_parts) > 1:
        video_id = _sanitize_youtube_id(path_parts[1])
    elif path_parts and re.match(r"^[0-9A-Za-z_-]{11}$", path_parts[0]):
        video_id = _sanitize_youtube_id(path_parts[0])

    channel_id = None
    if "channel" in qs and qs["channel"]:
        channel_candidate = _sanitize_youtube_id(qs["channel"][0])
        if channel_candidate:
            channel_id = channel_candidate

    if "list" in qs:
        playlist_id = _sanitize_youtube_id(qs["list"][0])
    if "index" in qs:
        try:
            playlist_index = int(qs["index"][0])
        except ValueError:
            playlist_index = None
    start_seconds = None
    for key in ("t", "start"):
        if key in qs:
            start_seconds = _parse_start_time(qs[key][0])
            if start_seconds is not None:
                break
    if start_seconds is None and parsed.fragment:
        frag_qs = parse_qs(parsed.fragment)
        for key in ("t", "start"):
            if key in frag_qs:
                start_seconds = _parse_start_time(frag_qs[key][0])
                if start_seconds is not None:
                    break

    if channel_id is None:
        for idx, part in enumerate(path_parts):
            if part.lower() == "channel" and idx + 1 < len(path_parts):
                channel_candidate = _sanitize_youtube_id(path_parts[idx + 1])
                if channel_candidate:
                    channel_id = channel_candidate
                    break

    details.update(
        {
            "video_id": video_id,
            "playlist_id": playlist_id,
            "playlist_index": playlist_index,
            "start_seconds": start_seconds,
            "channel_id": channel_id,
        }
    )
    return details


def build_youtube_embed_url(
    video_id: str,
    playlist_id: Optional[str] = None,
    playlist_index: Optional[int] = None,
    start_seconds: Optional[int] = None,
) -> str:
    params = {}
    if playlist_id:
        params["list"] = playlist_id
        if playlist_index is not None:
            params["index"] = max(0, playlist_index)
    if start_seconds:
        params["start"] = max(0, start_seconds)
    query = urlencode(params, doseq=True)
    base = f"https://www.youtube-nocookie.com/embed/{video_id}"
    return f"{base}?{query}" if query else base


def build_youtube_live_embed_url(channel_id: str) -> str:
    return f"https://www.youtube.com/embed/live_stream?channel={channel_id}"


def _extract_youtube_hls(url: str, video_id: Optional[str]) -> Optional[str]:
    """
    Attempt to resolve a direct HLS manifest for a YouTube broadcast (live or VOD).
    Returns the best .m3u8 URL when available.
    """
    if not _YT_DLP_AVAILABLE:
        return None

    target = url
    if video_id:
        target = f"https://www.youtube.com/watch?v={video_id}"

    opts = {
        "skip_download": True,
        "quiet": True,
        "nocheckcertificate": True,
        "noplaylist": True,
    }
    try:  # pragma: no cover - network-less failures handled in tests via monkeypatch
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(target, download=False)
    except Exception as exc:  # pragma: no cover - error path verified in tests
        logger.warning("yt_dlp live extraction failed for %s: %s", target, exc)
        return None

    def _score(fmt: Dict[str, Any]) -> int:
        height = fmt.get("height") or 0
        tbr = fmt.get("tbr") or 0
        return int(height) * 1000 + int(tbr)

    formats = info.get("formats") or []
    candidates: list[Tuple[int, str]] = []
    for fmt in formats:
        fmt_url = fmt.get("url") or ""
        if not fmt_url:
            continue
        protocol = (fmt.get("protocol") or "").lower()
        ext = (fmt.get("ext") or "").lower()
        if "m3u8" in protocol or "m3u8" in fmt_url or ext == "m3u8":
            candidates.append((_score(fmt), fmt_url))

    if not candidates:
        fallback_url = info.get("url")
        if isinstance(fallback_url, str) and "m3u8" in fallback_url:
            return fallback_url
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def youtube_oembed_lookup(url: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve metadata from the YouTube oEmbed endpoint with basic caching.
    Returns parsed JSON on success or None on failure.
    """
    cache_key = url.strip()
    now = time.time()
    with _cache_lock:
        cached = _oembed_cache.get(cache_key)
        if cached:
            ts, data = cached
            if now - ts < OEMBED_CACHE_TTL:
                return data
            del _oembed_cache[cache_key]

    params = {"url": url, "format": "json"}
    try:
        resp = requests.get(OEMBED_ENDPOINT, params=params, timeout=6)
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception:
        return None

    with _cache_lock:
        _oembed_cache[cache_key] = (now, data)
    return data


def _looks_like_hls(url: str) -> bool:
    lowered = url.lower()
    if any(token in lowered for token in (".m3u8", "format=m3u8", "playlist.m3u")):
        return True
    if not _YT_DLP_AVAILABLE:
        return False
    try:  # pragma: no cover - slow path rarely hit in tests
        ydl_opts = {"skip_download": True, "quiet": True, "nocheckcertificate": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        formats = info.get("formats") or []
        for fmt in formats:
            protocol = fmt.get("protocol") or ""
            if "m3u8" in protocol:
                return True
            fmt_url = fmt.get("url") or ""
            if ".m3u8" in fmt_url:
                return True
    except Exception:
        pass
    return False


def classify_url(url: str) -> EmbedMetadata:
    """
    Determine how EchoView should embed the given URL. Classification attempts:
    1. YouTube video/playlist/live
    2. HLS stream (.m3u8 or detected via yt_dlp)
    3. Fallback generic iframe
    """
    normalized = url.strip()
    if not normalized:
        return EmbedMetadata(
            embed_type="iframe",
            original_url=url,
            canonical_url=url,
            provider=None,
            title=None,
            content_type=None,
        )

    yt_details = parse_youtube_url_details(normalized)
    if yt_details["is_youtube"] and yt_details["video_id"]:
        provider = "YouTube"
        title = None
        thumbnail = None
        content_type = "video"
        channel_id = yt_details.get("channel_id")

        data = youtube_oembed_lookup(normalized)
        if data:
            provider = data.get("provider_name") or provider
            title = data.get("title") or title
            thumbnail = data.get("thumbnail_url")
            html = data.get("html") or ""
            if "playlist" in html and yt_details.get("playlist_id"):
                content_type = "playlist"
            if "live" in html or "is_live" in html:
                content_type = "live"
            for key in ("author_url", "provider_url"):
                candidate = data.get(key)
                if candidate:
                    extracted = parse_youtube_url_details(candidate).get("channel_id")
                    if extracted:
                        channel_id = channel_id or extracted
                        break

        canonical: str
        embed_type = "youtube"
        if content_type == "live":
            hls_url = _extract_youtube_hls(normalized, yt_details["video_id"])
            if hls_url:
                return EmbedMetadata(
                    embed_type="hls",
                    original_url=normalized,
                    canonical_url=hls_url,
                    provider=provider,
                    title=title or yt_details["video_id"],
                    content_type=content_type,
                    video_id=yt_details["video_id"],
                    playlist_id=yt_details.get("playlist_id"),
                    channel_id=channel_id,
                    start_seconds=None,
                    thumbnail_url=thumbnail,
                )
            embed_type = "mpv"
            canonical = normalized
            logger.warning(
                "Unable to resolve HLS manifest for live YouTube stream %s; falling back to mpv playback.",
                normalized,
            )
        else:
            canonical = build_youtube_embed_url(
                yt_details["video_id"],
                yt_details.get("playlist_id"),
                yt_details.get("playlist_index"),
                yt_details.get("start_seconds"),
            )

        return EmbedMetadata(
            embed_type=embed_type,
            original_url=normalized,
            canonical_url=canonical,
            provider=provider,
            title=title or yt_details["video_id"],
            content_type=content_type,
            video_id=yt_details["video_id"],
            playlist_id=yt_details.get("playlist_id"),
            channel_id=channel_id,
            start_seconds=yt_details.get("start_seconds"),
            thumbnail_url=thumbnail,
        )

    if _looks_like_hls(normalized):
        return EmbedMetadata(
            embed_type="hls",
            original_url=normalized,
            canonical_url=normalized,
            provider="HLS",
            title=None,
            content_type="video",
        )

    return EmbedMetadata(
        embed_type="iframe",
        original_url=normalized,
        canonical_url=normalized,
        provider=None,
        title=None,
        content_type="website",
    )


def serialize_embed_metadata(metadata: Optional[EmbedMetadata]) -> Optional[Dict[str, Any]]:
    if metadata is None:
        return None
    return metadata.to_dict()


def deserialize_embed_metadata(data: Optional[Dict[str, Any]]) -> Optional[EmbedMetadata]:
    return EmbedMetadata.from_dict(data)


def reset_oembed_cache() -> None:
    """Testing helper: clear the oEmbed cache."""
    with _cache_lock:
        _oembed_cache.clear()


def dump_oembed_cache() -> Dict[str, Any]:
    """Debug helper returning a shallow copy of the cache state."""
    with _cache_lock:
        return {k: {"timestamp": ts, "data": json.dumps(data)} for k, (ts, data) in _oembed_cache.items()}
