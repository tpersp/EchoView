import importlib
import types

tvm = importlib.import_module("tests.test_video_mode")
DisplayWindow = tvm.DisplayWindow
viewer = importlib.import_module("echoview.viewer")


def _classify(url):
    dw = DisplayWindow.__new__(DisplayWindow)
    return DisplayWindow.classify_url(dw, url)


def _make_stub_window():
    dw = DisplayWindow.__new__(DisplayWindow)
    dw.current_movie = None
    dw.handling_gif_frames = False
    dw.current_video_proc = None
    dw.disp_cfg = {}
    dw.cfg = {}
    dw.last_displayed_path = None

    class _Label:
        def __init__(self):
            self.movie = None
            self.cleared = False

        def clear(self):
            self.cleared = True

        def setMovie(self, movie):
            self.movie = movie

        def hide(self):
            pass

    class _HideOnly:
        def hide(self):
            pass

    class _Timer:
        def __init__(self):
            self.stopped = False
            self.started = False

        def stop(self):
            self.stopped = True

        def start(self):
            self.started = True

    class _WebView:
        def __init__(self):
            self.loaded = None
            self.hide_called = False
            self.show_called = False

        def load(self, url):
            self.loaded = url

        def show(self):
            self.show_called = True

        def hide(self):
            self.hide_called = True

    dw.foreground_label = _Label()
    dw.spotify_info_label = _HideOnly()
    dw.spotify_progress_bar = _HideOnly()
    dw.slideshow_timer = _Timer()
    dw.spotify_progress_timer = _Timer()
    dw.mpv_poll_timer = _Timer()
    dw.web_view = _WebView()
    dw.stop_current_video = lambda: None
    dw.clear_foreground_label = lambda msg: (_ for _ in ()).throw(AssertionError(f"clear_foreground_label called: {msg}"))
    return dw


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


def test_handle_remote_youtube_prefers_mpv(monkeypatch):
    dw = _make_stub_window()
    launched = []

    def fake_build(self, src):
        launched.append(src)
        return ["mpv", src]

    class DummyProc:
        def wait(self):
            pass

    stop_calls = []

    def stop_current_video():
        stop_calls.append("stop")
        dw.current_video_proc = None

    dw.stop_current_video = stop_current_video

    monkeypatch.setattr(viewer.shutil, "which", lambda _: True)
    monkeypatch.setattr(viewer.DisplayWindow, "build_mpv_command", fake_build)
    monkeypatch.setattr(viewer.subprocess, "Popen", lambda cmd: DummyProc())
    monkeypatch.setattr(
        viewer.threading,
        "Thread",
        lambda target, args, daemon=True: types.SimpleNamespace(start=lambda: target(*args)),
    )
    monkeypatch.setattr(viewer, "QUrl", lambda url: url)

    dw.handle_remote_url("https://www.youtube.com/watch?v=Xy123")

    assert launched == ["https://www.youtube.com/watch?v=Xy123"]
    assert dw.web_view.loaded is None
    assert dw.web_view.show_called is False
    assert stop_calls[0] == "stop"


def test_handle_remote_youtube_fallback_to_embed(monkeypatch):
    dw = _make_stub_window()

    dw.web_view.loaded = None
    dw.web_view.show_called = False

    monkeypatch.setattr(viewer.shutil, "which", lambda _: False)
    monkeypatch.setattr(
        viewer.DisplayWindow,
        "build_mpv_command",
        lambda self, src: (_ for _ in ()).throw(AssertionError("mpv command should not be built")),
    )
    monkeypatch.setattr(viewer, "QUrl", lambda url: url)

    dw.handle_remote_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert dw.web_view.loaded.startswith("https://www.youtube.com/embed/dQw4w9WgXcQ")
    assert "autoplay=1" in dw.web_view.loaded
    assert "mute=1" in dw.web_view.loaded
    assert dw.web_view.show_called is True


class DummyResponse:
    def __init__(self, text="", json_data=None, content_type="text/html"):
        self.text = text
        self._json_data = json_data
        self.headers = {"Content-Type": content_type}
        self.ok = True

    def json(self):
        if self._json_data is None:
            raise ValueError("No JSON payload")
        return self._json_data


def test_resolve_embed_from_group_page(monkeypatch):
    dw = _make_stub_window()
    group_url = "http://example.com/stream/group/lofi-pip"
    stream_url = "http://example.com/stream/stream1"
    settings_url = "http://example.com/get-settings/stream1"

    responses = {
        group_url: DummyResponse('<iframe src="/stream/stream1"></iframe>'),
        stream_url: DummyResponse('<script>const streamId = "stream1";</script>'),
        settings_url: DummyResponse("", json_data={"stream_url": "https://www.youtube.com/watch?v=abc123"}, content_type="application/json"),
    }

    def fake_get(url, timeout=5):
        if url not in responses:
            raise AssertionError(f"Unexpected URL: {url}")
        return responses[url]

    fake_requests = types.SimpleNamespace(get=fake_get)
    monkeypatch.setattr(viewer, "requests", fake_requests)

    info = DisplayWindow._resolve_embed_from_page(dw, group_url)
    assert info is not None
    assert info["kind"] == "youtube"
    assert "youtube.com/embed/abc123" in info["target"]
    assert info["source"] == "https://www.youtube.com/watch?v=abc123"
    assert info["prefer_page"] is True


def test_handle_remote_group_page_shows_page(monkeypatch):
    dw = _make_stub_window()
    group_url = "http://example.com/stream/group/lofi-pip"
    stream_url = "http://example.com/stream/stream1"
    settings_url = "http://example.com/get-settings/stream1"

    responses = {
        group_url: DummyResponse('<iframe src="/stream/stream1"></iframe>'),
        stream_url: DummyResponse('<script>const streamId = "stream1";</script>'),
        settings_url: DummyResponse("", json_data={"stream_url": "https://www.youtube.com/watch?v=abc123"}, content_type="application/json"),
    }

    def fake_get(url, timeout=5):
        if url not in responses:
            raise AssertionError(f"Unexpected URL: {url}")
        return responses[url]

    fake_requests = types.SimpleNamespace(get=fake_get)
    monkeypatch.setattr(viewer, "requests", fake_requests)
    launch_calls = []

    def fake_launch(self, src, show_error=True):
        launch_calls.append((src, show_error))
        return True

    monkeypatch.setattr(viewer.DisplayWindow, "_launch_remote_video", fake_launch)
    monkeypatch.setattr(viewer, "QUrl", lambda url: url)

    dw.handle_remote_url(group_url)

    assert launch_calls == []
    assert dw.web_view.loaded == group_url
    assert dw.web_view.show_called is True
