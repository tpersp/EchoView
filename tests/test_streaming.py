from types import SimpleNamespace
import subprocess

import pytest

from echoview import streaming, browser, embed_utils


def test_retry_budget_is_finite():
    policy = streaming.RetryPolicy()
    assert [policy.next_delay() for _ in range(5)] == [2000, 5000, None, None, None]


def test_formats_remain_bounded_and_respect_profile_and_quality():
    assert streaming.stream_height({"resource_profile": "pi3", "youtube_quality": "highres"}) == 480
    assert streaming.stream_height({"youtube_quality": "default"}, 720) == 720
    assert streaming.stream_height({"youtube_quality": "medium"}, 1080) == 360
    for alternative in streaming.format_selector(480).split("/"):
        assert "height<=480" in alternative
    assert "vcodec^=avc1" in streaming.format_selector(480)


def test_stream_flags_honor_audio_pause_and_start():
    flags = streaming.stream_flags({"youtube_autoplay": False, "youtube_mute": False, "youtube_captions": True}, True, 720, 90)
    assert "--mute=no" in flags and "--pause=yes" in flags
    assert "--sub-visibility=yes" in flags and "--start=90" in flags
    assert "--network-timeout=10" in flags
    assert any(flag.startswith("--script=") and flag.endswith("mpv_observer.lua") for flag in flags)


def test_capability_check_reports_versions_without_paths_or_stderr(monkeypatch):
    versions = {"yt-dlp": "2026.10.26", "yt-dlp-ejs": "0.8.0", "deno": "2.9.8"}
    monkeypatch.setattr(streaming.metadata, "version", versions.__getitem__)
    monkeypatch.setattr(streaming, "tool_path", lambda name: "/private/" + name)
    def run(args, **kwargs):
        assert args == ["/private/deno", "--version"]
        assert kwargs["timeout"] == 5
        return SimpleNamespace(stdout="deno 2.9.8 (stable)\n", stderr="private-cookie")
    monkeypatch.setattr(streaming.subprocess, "run", run)
    report = streaming.capabilities()
    assert report["ready"] and report["deno_version"] == "2.9.8"
    assert "/private/" not in str(report) and "private-cookie" not in str(report)


def test_fast_gui_capability_check_never_launches_a_process(monkeypatch):
    monkeypatch.setattr(streaming.metadata, "version", lambda name: "2.9.8" if name == "deno" else "installed")
    monkeypatch.setattr(streaming, "tool_path", lambda name: name)
    monkeypatch.setattr(streaming.subprocess, "run", lambda *a, **kw: pytest.fail("GUI runtime probe"))
    report = streaming.capabilities(probe_runtime=False)
    assert report["ready"] and not report["runtime_probed"]


def test_broken_runtime_is_reported_not_assumed_ready(monkeypatch):
    monkeypatch.setattr(streaming.metadata, "version", lambda name: "2.9.8")
    monkeypatch.setattr(streaming, "tool_path", lambda name: name)
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 5)
    monkeypatch.setattr(streaming.subprocess, "run", timeout)
    report = streaming.capabilities()
    assert not report["ready"] and "Deno 2.9.8+ runtime" in report["missing"]


def test_browser_defaults_use_engine_identity_and_keep_custom_overrides(monkeypatch):
    assert browser.qt_flags(browser.LEGACY_QT_FLAGS) == browser.DEFAULT_QT_FLAGS
    assert browser.qt_flags("--disable-gpu") == "--disable-gpu"
    assert "--user-agent" not in browser.qt_flags(None)
    monkeypatch.setenv("ECHOVIEW_CHROMIUM_FLAGS", '--disable-gpu --user-agent="Custom Agent"')
    assert browser.chromium_flags() == ["--disable-gpu", "--user-agent=Custom Agent"]


def test_classification_never_extracts_or_requests_by_default(monkeypatch):
    monkeypatch.setattr(embed_utils.requests, "get", lambda *a, **kw: pytest.fail("classification network request"))
    for source, kind in [("https://youtube.com/watch?v=abc123def45", "youtube"),
                         ("https://youtube.com/@example/live", "youtube"),
                         ("https://example.test/live.m3u8?token=temporary", "hls"),
                         ("https://example.test/home", "iframe")]:
        assert embed_utils.classify_url(source).embed_type == kind


def test_legacy_signed_manifest_is_ignored_and_not_reserialized():
    payload = {"embed_type": "hls", "original_url": "https://youtube.com/watch?v=abc123def45",
               "canonical_url": "https://cdn.example/live.m3u8?expire=1&token=private", "content_type": "live"}
    metadata = embed_utils.deserialize_embed_metadata(payload)
    assert metadata.embed_type == "youtube" and metadata.video_id == "abc123def45"
    assert metadata.original_url == payload["original_url"]
    serialized = embed_utils.serialize_embed_metadata(metadata)
    assert "expire=" not in str(serialized) and "private" not in str(serialized)


def test_channel_playlist_and_bare_hostname_urls():
    assert embed_utils.parse_youtube_url_details("youtu.be/abc123def45")["video_id"] == "abc123def45"
    meta = embed_utils.classify_url("https://www.youtube.com/embed/live_stream?channel=UCfixture")
    assert meta.video_id is None and meta.channel_id == "UCfixture"
    meta = embed_utils.classify_url("https://youtube.com/playlist?list=PLfixture")
    assert meta.playlist_id == "PLfixture" and "videoseries" in meta.canonical_url
    assert embed_utils.classify_url("https://youtube.com.evil.test/watch?v=abc123def45").embed_type == "iframe"


def test_real_extractor_format_selection_uses_fixture_only():
    yt_dlp = pytest.importorskip("yt_dlp")
    formats = [{"format_id": str(height), "url": f"https://fixture.invalid/{height}", "height": height,
                "width": height * 16 // 9, "vcodec": "avc1.42001e", "acodec": "none", "ext": "mp4"}
               for height in (360, 480, 1080)]
    formats.append({"format_id": "audio", "url": "https://fixture.invalid/audio", "vcodec": "none", "acodec": "mp4a.40.2", "ext": "m4a"})
    with yt_dlp.YoutubeDL({"format": streaming.format_selector(480), "quiet": True,
                           "no_warnings": True, "cachedir": False}) as ydl:
        result = ydl.process_ie_result({"id": "fixture", "title": "Fixture", "formats": formats}, download=False)
    assert result["height"] == 480


def test_retry_budget_resets_only_after_sustained_playback():
    now = [100]
    policy = streaming.RetryPolicy(clock=lambda: now[0])
    assert policy.next_delay() == 2000
    policy.mark_started()
    now[0] += 10
    assert policy.next_delay() == 5000
    assert policy.next_delay() is None
    policy.mark_started()
    now[0] += 61
    assert policy.next_delay() == 2000


def test_player_events_require_the_exact_observer_prefix():
    assert streaming.parse_player_event("[mpv_observer] ECHOVIEW_PLAYBACK_STARTED|10.5\n") == "playing"
    assert streaming.parse_player_event("[mpv_observer] ECHOVIEW_PLAYBACK_STARTED|N/A\n") == "playing_live"
    assert streaming.parse_player_event("[cplayer] command --term-playing-msg=ECHOVIEW_PLAYBACK_STARTED|1") is None
