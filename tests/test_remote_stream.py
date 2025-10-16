import importlib

tvm = importlib.import_module("tests.test_video_mode")
DisplayWindow = tvm.DisplayWindow


def _classify(url):
    dw = DisplayWindow.__new__(DisplayWindow)
    return DisplayWindow.classify_url(dw, url)


def test_classify_youtube_watch():
    kind, target = _classify("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert kind == "youtube"
    assert "youtube.com/embed/dQw4w9WgXcQ" in target


def test_classify_youtube_short_link():
    kind, target = _classify("https://youtu.be/dQw4w9WgXcQ?si=abc123")
    assert kind == "youtube"
    assert target.startswith("https://www.youtube.com/embed/dQw4w9WgXcQ")
    assert "si=abc123" in target


def test_classify_twitch_channel():
    kind, target = _classify("https://www.twitch.tv/somechannel")
    assert kind == "twitch"
    assert "player.twitch.tv" in target
    assert "channel=somechannel" in target


def test_classify_hls_manifest_with_query():
    url = "https://cdn.example.com/live/stream.m3u8?token=abc"
    kind, target = _classify(url)
    assert kind == "hls"
    assert target == url


def test_classify_direct_video_extension():
    kind, target = _classify("https://media.example.com/video.MP4")
    assert kind == "video"
    assert target.lower().endswith(".mp4")


def test_classify_default_website():
    kind, target = _classify("https://example.com/page")
    assert kind == "website"
    assert target == "https://example.com/page"
