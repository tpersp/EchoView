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
from dataclasses import dataclass, asdict, replace
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests

YOUTUBE_DOMAINS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "gaming.youtube.com",
    "youtu.be",
    "www.youtu.be",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
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
        return normalize_metadata(cls(
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
        ))


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
    normalized = url.strip()
    parsed = urlparse(normalized if "://" in normalized else "https://" + normalized)
    details: Dict[str, Any] = {
        "is_youtube": False,
        "video_id": None,
        "playlist_id": None,
        "playlist_index": None,
        "start_seconds": None,
        "channel_id": None,
    }
    if not parsed.hostname or not _is_youtube_host(parsed.hostname):
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
    elif path_parts[:2] in (["embed", "live_stream"], ["embed", "videoseries"]):
        pass
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
        while len(_oembed_cache) > 128:
            _oembed_cache.pop(next(iter(_oembed_cache)))
    return data


def _looks_like_hls(url: str) -> bool:
    lowered = url.lower()
    return any(token in lowered for token in (".m3u8", "format=m3u8", "playlist.m3u"))


def classify_url(url: str, enrich: bool = False) -> EmbedMetadata:
    """Classify stable sources without extraction; enrichment is explicit/bounded."""
    normalized = url.strip()
    if normalized and "://" not in normalized:
        normalized = "https://" + normalized
    details = parse_youtube_url_details(normalized)
    path = urlparse(normalized).path
    live = "/live" in path or "/embed/live_stream" in path
    if details["is_youtube"] and (details["video_id"] or details["playlist_id"] or details["channel_id"] or live):
        data = (youtube_oembed_lookup(normalized) or {}) if enrich else {}
        live = live or "is_live" in data.get("html", "")
        channel = details["channel_id"]
        for key in ("author_url", "provider_url"):
            if data.get(key):
                channel = channel or parse_youtube_url_details(data[key]).get("channel_id")
        if details["video_id"]:
            canonical = build_youtube_embed_url(details["video_id"], details["playlist_id"],
                                                details["playlist_index"], details["start_seconds"])
        elif channel:
            canonical = build_youtube_live_embed_url(channel)
        elif details["playlist_id"]:
            canonical = "https://www.youtube-nocookie.com/embed/videoseries?" + urlencode({"list": details["playlist_id"]})
        else:
            canonical = normalized
        return EmbedMetadata(
            embed_type="youtube", original_url=normalized, canonical_url=canonical,
            provider=data.get("provider_name") or "YouTube", title=data.get("title") or details["video_id"],
            content_type="live" if live else ("playlist" if details["playlist_id"] else "video"),
            video_id=details["video_id"], playlist_id=details["playlist_id"], channel_id=channel,
            start_seconds=details["start_seconds"], thumbnail_url=data.get("thumbnail_url"),
        )
    if _looks_like_hls(normalized):
        return EmbedMetadata("hls", normalized, normalized, provider="HLS", content_type="video")
    return EmbedMetadata("iframe", normalized, normalized, content_type="website")


def normalize_metadata(metadata: EmbedMetadata) -> EmbedMetadata:
    """Ignore historical signed YouTube manifests; never persist them again."""
    details = parse_youtube_url_details(metadata.original_url)
    if details["is_youtube"] and (metadata.embed_type in ("hls", "mpv")
            or not _is_youtube_host(urlparse(metadata.canonical_url).hostname or "")
            or _looks_like_hls(metadata.canonical_url)):
        stable = classify_url(metadata.original_url)
        return replace(metadata, embed_type="youtube", canonical_url=stable.canonical_url,
                       video_id=metadata.video_id or stable.video_id,
                       playlist_id=metadata.playlist_id or stable.playlist_id,
                       channel_id=metadata.channel_id or stable.channel_id)
    return metadata


def serialize_embed_metadata(metadata: Optional[EmbedMetadata]) -> Optional[Dict[str, Any]]:
    if metadata is None:
        return None
    return normalize_metadata(metadata).to_dict()


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


def playback_embed_url(metadata, settings, origin):
    base_url = metadata.canonical_url or metadata.original_url or settings.get("web_url", "")
    if not base_url:
        return ""
    parsed = urlparse(base_url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    is_live = (metadata.content_type or "").lower() == "live"

    if is_live:
        for param in ("list", "index", "start", "t", "feature"):
            query.pop(param, None)

    autoplay = "1" if settings.get("youtube_autoplay", True) else "0"
    mute = "1" if settings.get("youtube_mute", True) else "0"
    query["autoplay"] = [autoplay]
    query["mute"] = [mute]
    if settings.get("youtube_captions", False):
        query["cc_load_policy"] = ["1"]
    else:
        query.pop("cc_load_policy", None)

    quality = settings.get("youtube_quality", "default")
    if quality and quality != "default":
        query["vq"] = [quality]
    else:
        query.pop("vq", None)

    # Reasonable defaults to keep the player inline without recommended videos.
    query.setdefault("playsinline", ["1"])
    query.setdefault("rel", ["0"])
    query.setdefault("modestbranding", ["1"])
    query.setdefault("enablejsapi", ["1"])
    if not is_live:
        query.setdefault("feature", ["oembed"])
    else:
        query.pop("feature", None)
    query["origin"] = [origin]

    new_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))
