import pathlib
import sys

import pathlib
import sys
from urllib.parse import urlparse

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from echoview import embed_utils


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def clear_cache():
    embed_utils.reset_oembed_cache()
    yield
    embed_utils.reset_oembed_cache()


def test_parse_youtube_watch_url_details():
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=1m10s"
    details = embed_utils.parse_youtube_url_details(url)
    assert details["is_youtube"] is True
    assert details["video_id"] == "dQw4w9WgXcQ"
    assert details["playlist_id"] is None
    assert details["start_seconds"] == 70


def test_parse_youtu_be_short_link_with_playlist():
    url = "https://youtu.be/dQw4w9WgXcQ?list=PL12345&index=3"
    details = embed_utils.parse_youtube_url_details(url)
    assert details["video_id"] == "dQw4w9WgXcQ"
    assert details["playlist_id"] == "PL12345"
    assert details["playlist_index"] == 3


def test_classify_youtube_url_uses_oembed(monkeypatch):
    url = "https://www.youtube.com/watch?v=abc123def45"

    def fake_get(endpoint, params=None, timeout=0):
        assert endpoint == embed_utils.OEMBED_ENDPOINT
        assert params["url"] == url
        return _FakeResponse(
            payload={
                "provider_name": "YouTube",
                "title": "Sample Video",
                "html": '<iframe src="https://www.youtube.com/embed/abc123def45"></iframe>',
                "thumbnail_url": "https://img.youtube.com/vi/abc123def45/default.jpg",
            }
        )

    monkeypatch.setattr(embed_utils.requests, "get", fake_get)
    meta = embed_utils.classify_url(url)

    assert meta.embed_type == "youtube"
    assert meta.video_id == "abc123def45"
    parsed = urlparse(meta.canonical_url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "www.youtube-nocookie.com"
    assert parsed.path == "/embed/abc123def45"
    assert meta.provider == "YouTube"
    assert meta.title == "Sample Video"
    assert meta.thumbnail_url.endswith("default.jpg")


def test_classify_hls_by_extension():
    url = "https://example.com/live/channel.m3u8"
    meta = embed_utils.classify_url(url)
    assert meta.embed_type == "hls"
    assert meta.canonical_url == url


def test_embed_metadata_roundtrip():
    meta = embed_utils.EmbedMetadata(
        embed_type="youtube",
        original_url="https://youtube.com/watch?v=abc",
        canonical_url="https://www.youtube.com/embed/abc",
        provider="YouTube",
        title="Demo",
        content_type="video",
        video_id="abc",
        playlist_id=None,
        start_seconds=12,
        thumbnail_url="https://img.youtube.com/vi/abc/default.jpg",
    )
    payload = embed_utils.serialize_embed_metadata(meta)
    restored = embed_utils.deserialize_embed_metadata(payload)
    assert restored == meta
