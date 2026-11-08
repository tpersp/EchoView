import sys
import os
import types
import time

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "echoview"))

# Provide dummy PySide6 modules so echoview can be imported without the real Qt deps
qtcore = types.ModuleType("PySide6.QtCore")
qtcore.Signal = lambda *args: None
class DummyQt:
    AlignCenter = 0
    AlignLeft = 0
    AlignRight = 0
    AlignHCenter = 0
    AlignVCenter = 0
    TextWordWrap = 0
    CompositionMode_Difference = 0
    FramelessWindowHint = 0
    KeepAspectRatio = 0
    FastTransformation = 0
    IgnoreAspectRatio = 0
    SmoothTransformation = 0
    white = 0
    transparent = 0
qtcore.Qt = DummyQt
class DummyTimer:
    def __init__(self, *a, **k):
        pass
    @staticmethod
    def singleShot(ms, func):
        func()
qtcore.QTimer = DummyTimer
qtcore.Slot = lambda *a, **k: (lambda f: f)
qtcore.QSize = object
qtcore.QRect = object
qtcore.QRectF = object
qtcore.QUrl = object

qtgui = types.ModuleType("PySide6.QtGui")
for name in ["QPixmap", "QMovie", "QPainter", "QImage", "QImageReader", "QTransform", "QFont"]:
    setattr(qtgui, name, type(name, (), {}))

qtwidgets = types.ModuleType("PySide6.QtWidgets")
for name in [
    "QApplication",
    "QMainWindow",
    "QWidget",
    "QLabel",
    "QProgressBar",
    "QGraphicsScene",
    "QGraphicsPixmapItem",
    "QGraphicsBlurEffect",
    "QSizePolicy",
]:
    setattr(qtwidgets, name, type(name, (), {}))

qtweb = types.ModuleType("PySide6.QtWebEngineWidgets")
qtweb.QWebEngineView = type("QWebEngineView", (), {})

qtwebcore = types.ModuleType("PySide6.QtWebEngineCore")


class _DummyWebEngineSettings:
    PlaybackRequiresUserGesture = 0

    @staticmethod
    def defaultSettings():
        return types.SimpleNamespace(setAttribute=lambda *a, **k: None)


qtwebcore.QWebEngineSettings = _DummyWebEngineSettings

qtmultimedia = types.ModuleType("PySide6.QtMultimedia")


class _DummyAudioOutput:
    def __init__(self, *args, **kwargs):
        pass

    def setVolume(self, *args, **kwargs):
        pass

    def setMuted(self, *args, **kwargs):
        pass


class _DummyMediaPlayer:
    def __init__(self, *args, **kwargs):
        pass

    def setAudioOutput(self, *args, **kwargs):
        pass

    def setVideoOutput(self, *args, **kwargs):
        pass

    def setSource(self, *args, **kwargs):
        pass

    def play(self):
        pass

    def stop(self):
        pass


qtmultimedia.QAudioOutput = _DummyAudioOutput
qtmultimedia.QMediaPlayer = _DummyMediaPlayer

qtmultimedia_widgets = types.ModuleType("PySide6.QtMultimediaWidgets")


class _DummyVideoWidget:
    def __init__(self, *args, **kwargs):
        pass

    def hide(self):
        pass

    def show(self):
        pass

    def setGeometry(self, *args, **kwargs):
        pass

    def lower(self):
        pass


qtmultimedia_widgets.QVideoWidget = _DummyVideoWidget

spotipy = types.ModuleType("spotipy")
spotipy.Spotify = type("Spotify", (), {})
oauth2 = types.ModuleType("spotipy.oauth2")
oauth2.SpotifyOAuth = type("SpotifyOAuth", (), {})
spotipy.oauth2 = oauth2

sys.modules.setdefault("PySide6", types.ModuleType("PySide6"))
sys.modules.setdefault("PySide6.QtCore", qtcore)
sys.modules.setdefault("PySide6.QtGui", qtgui)
sys.modules.setdefault("PySide6.QtWidgets", qtwidgets)
sys.modules.setdefault("PySide6.QtWebEngineCore", qtwebcore)
sys.modules.setdefault("PySide6.QtWebEngineWidgets", qtweb)
sys.modules.setdefault("PySide6.QtMultimedia", qtmultimedia)
sys.modules.setdefault("PySide6.QtMultimediaWidgets", qtmultimedia_widgets)
sys.modules.setdefault("spotipy", spotipy)
sys.modules.setdefault("spotipy.oauth2", oauth2)

import echoview

DisplayWindow = echoview.DisplayWindow


def test_spotify_fetch_nonblocking_and_single(monkeypatch):
    import threading
    from echoview import viewer
    from echoview.spotify_client import Playback
    entered = threading.Event()
    release = threading.Event()
    delivered = threading.Event()
    results = []
    class Poller:
        def fetch(self):
            entered.set()
            assert release.wait(2)
            return Playback("paused")
    class Signal:
        def emit(self, fid, result):
            results.append((fid, result))
            delivered.set()
    monkeypatch.setattr(viewer, "shared_poller", lambda: Poller())
    dw = DisplayWindow.__new__(DisplayWindow)
    dw.spotify_fetch_pending = None
    dw.spotify_fetch_id = 0
    dw.spotify_result = Signal()
    dw.start_spotify_fetch()
    assert entered.wait(1)  # GUI call returned while the request is still blocked.
    dw.start_spotify_fetch()
    assert dw.spotify_fetch_id == 1
    assert not results
    release.set()
    assert delivered.wait(1)
    assert results[0][0] == 1
    assert results[0][1].status == "paused"


def test_stale_and_closed_window_results_are_ignored():
    from echoview.spotify_client import Playback
    dw = DisplayWindow.__new__(DisplayWindow)
    dw.running = True
    dw.current_mode = "spotify"
    dw.spotify_fetch_pending = 1
    dw.spotify_fetch_id = 2  # Settings were reloaded while the request ran.
    dw.render_spotify = lambda path: (_ for _ in ()).throw(AssertionError("stale render"))
    dw.handle_spotify_result(1, Playback("playing"))
    assert dw.spotify_fetch_pending is None
    dw.running = False
    dw.handle_spotify_result(2, Playback("playing"))
    dw.running = True
    dw.current_mode = "random_image"
    dw.handle_spotify_result(2, Playback("playing"))


def test_playback_progress_uses_monotonic_time(monkeypatch):
    from echoview import viewer
    values = []
    dw = DisplayWindow.__new__(DisplayWindow)
    dw.spotify_progress_bar = types.SimpleNamespace(setValue=values.append)
    dw.spotify_info = {"progress_ms": 1000, "duration_ms": 10000, "fetched_time": 10}
    monkeypatch.setattr(viewer.time, "monotonic", lambda: 12)
    dw.update_spotify_progress()
    assert values == [30]
    dw.spotify_info = None
    dw.update_spotify_progress()
    assert values[-1] == 0


def test_fallback_rotation_does_not_slow_polling(monkeypatch):
    from echoview import viewer
    now = [100]
    monkeypatch.setattr(viewer.time, "monotonic", lambda: now[0])
    shown = []
    hidden = types.SimpleNamespace(hide=lambda: None, stop=lambda: None, setText=lambda text: None)
    dw = DisplayWindow.__new__(DisplayWindow)
    dw.spotify_info = None
    dw.spotify_info_label = hidden
    dw.spotify_progress_bar = hidden
    dw.spotify_progress_timer = hidden
    dw.disp_cfg = {"fallback_mode": "random_image", "image_interval": 60}
    dw.fallback_image_list = ["first", "second"]
    dw.fallback_index = -1
    dw.show_foreground_image = shown.append
    dw.slideshow_timer = types.SimpleNamespace(setInterval=lambda ms: (_ for _ in ()).throw(AssertionError("polling slowed")))
    dw.render_spotify("")
    assert shown == ["first"]
    now[0] += 5
    dw.render_spotify("")
    assert shown == ["first"]
    now[0] += 55
    dw.render_spotify("")
    assert shown == ["first", "second"]


def test_gui_accepts_current_result_and_exposes_metadata(monkeypatch):
    from echoview import viewer
    from echoview.spotify_client import Playback
    monkeypatch.setattr(viewer, "log_message", lambda text: None)
    dw = DisplayWindow.__new__(DisplayWindow)
    dw.running = True
    dw.current_mode = "spotify"
    dw.spotify_fetch_id = dw.spotify_fetch_pending = 1
    rendered = []
    dw.render_spotify = rendered.append
    dw.handle_spotify_result(1, Playback("playing", song="Song", fetched_time=10))
    assert dw.spotify_fetch_pending is None
    assert dw.spotify_info["song"] == "Song"
    assert rendered == [""]  # Metadata remains available without artwork.
    dw.spotify_fetch_id = dw.spotify_fetch_pending = 2
    dw.handle_spotify_result(2, Playback("paused"))
    assert dw.spotify_info is None


def test_viewer_hotplug_preserves_settings_and_reuses_other_window(monkeypatch):
    from echoview import viewer, displays
    hdmi = types.SimpleNamespace(name=lambda: "HDMI-1")
    composite = types.SimpleNamespace(name=lambda: "Composite-1")
    screens = [hdmi, composite]
    cfg = {"displays": {"HDMI-1": displays.default_display("HDMI-1"),
                        "Composite-1": dict(displays.default_display("Composite-1"), specific_image="remember.png")}}
    found = {name: {"connected": True, "active": True, "current_mode": "720x576"}
             for name in cfg["displays"]}
    created = []
    class Window:
        def __init__(self, name, settings, screen):
            self.assigned_screen = screen
            self.closed = False
            created.append(name)
        def close(self):
            self.closed = True
        def show(self):
            pass
        def setWindowTitle(self, title):
            pass
        def setup_layout(self):
            pass
        def updateForegroundScaled(self):
            pass
    monkeypatch.setattr(viewer, "load_config", lambda: cfg)
    monkeypatch.setattr(viewer, "save_config", lambda cfg: None)
    monkeypatch.setattr(viewer, "discover_monitors", lambda: found)
    monkeypatch.setattr(viewer, "DisplayWindow", Window)
    gui = viewer.EchoViewGUI.__new__(viewer.EchoViewGUI)
    gui.app = types.SimpleNamespace(screens=lambda: screens)
    gui.window_by_connector = {}
    gui.windows = []
    gui.mode_attempts = set()
    gui._schedule_sync = lambda: None
    gui._sync_screens()
    assert created == ["HDMI-1", "Composite-1"]
    initial_hdmi = gui.window_by_connector["HDMI-1"]
    initial_composite = gui.window_by_connector["Composite-1"]
    screens[:] = [hdmi]
    gui._screen_removed(composite)
    gui._sync_screens()
    assert initial_composite.closed
    assert gui.window_by_connector["HDMI-1"] is initial_hdmi
    assert cfg["displays"]["Composite-1"]["specific_image"] == "remember.png"
    screens[:] = [composite, hdmi]
    gui._sync_screens()
    assert gui.window_by_connector["HDMI-1"] is initial_hdmi
    assert gui.window_by_connector["Composite-1"].assigned_screen is composite
    assert len(gui.windows) == 2


def test_video_player_uses_connector_name_and_physical_aspect():
    dw = DisplayWindow.__new__(DisplayWindow)
    dw.disp_name = "Composite-1"
    dw.disp_cfg = {"display_aspect": "auto"}
    dw.assigned_screen = types.SimpleNamespace(name=lambda: "Composite-1")
    cmd = dw.build_mpv_command("/tmp/video.mp4")
    assert "--fs-screen-name=Composite-1" in cmd
    assert "--screen-name=Composite-1" in cmd
    assert not any(arg.startswith("--fs-screen=") for arg in cmd)
    assert "--monitoraspect=4:3" in cmd


def test_embedded_video_uses_physical_display_geometry():
    from echoview.displays import fit_dimensions
    geometries = []
    modes = []
    size = types.SimpleNamespace(width=lambda: 1920, height=lambda: 1080)
    rect = types.SimpleNamespace(width=lambda: 720, height=lambda: 576, x=lambda: 0, y=lambda: 0)
    dw = DisplayWindow.__new__(DisplayWindow)
    dw.hls_video_widget = types.SimpleNamespace(
        videoSink=lambda: types.SimpleNamespace(videoSize=lambda: size),
        setAspectRatioMode=modes.append, setGeometry=lambda *args: geometries.append(args))
    dw.calc_fill_size = lambda iw, ih, fw, fh: fit_dimensions(iw, ih, fw, fh, 16 / 15)
    dw._layout_hls_video(rect)
    assert geometries == [(0, 72, 720, 432)]


def test_image_cache_byte_limit_and_profile_generation():
    import threading
    from collections import OrderedDict
    dw = DisplayWindow.__new__(DisplayWindow)
    dw.image_cache = OrderedDict()
    dw.cache_lock = threading.Lock()
    dw.cache_generation = 0
    dw.cache_capacity = 4
    dw.cache_budget = 10
    calls = []
    def load(path):
        calls.append(path)
        return {"bytes": 6, "image": path}
    dw.load_and_cache_image = load
    dw.get_cached_image("a")
    cached = dw.get_cached_image("b")
    assert list(dw.image_cache) == ["b"] and dw.cache_bytes == 6
    assert dw.get_cached_image("b") is cached
    assert calls == ["a", "b"]
    def old_worker(path):
        dw.cache_generation += 1  # Profile changed while preloading decoded.
        dw.image_cache.clear()
        return {"bytes": 6, "image": path}
    dw.load_and_cache_image = old_worker
    dw.get_cached_image("old")
    assert not dw.image_cache


def test_external_browser_safe_area_preserves_negative_screen_origin():
    dw = DisplayWindow.__new__(DisplayWindow)
    dw.disp_cfg = {"safe_area": {"left": 5, "right": 5, "top": 5, "bottom": 5}}
    geom = types.SimpleNamespace(x=lambda: -720, y=lambda: 24, width=lambda: 720, height=lambda: 576)
    dw.assigned_screen = types.SimpleNamespace(geometry=lambda: geom)
    flags = dw._chromium_window_flags()
    assert "--window-position=-684,53" in flags
    assert "--window-size=648,518" in flags


def test_stream_retries_use_original_source_and_cancel_stale_callbacks(monkeypatch):
    from echoview import viewer, embed_utils, streaming
    scheduled, played, fallback = [], [], []
    source = "https://youtube.com/watch?v=abc123def45"
    dw = DisplayWindow.__new__(DisplayWindow)
    dw.running = True
    dw.current_mode = "web_page"
    dw.stream_generation = 5
    dw.stream_source = source
    dw.stream_metadata = embed_utils.classify_url(source)
    dw.stream_retry = streaming.RetryPolicy()
    dw.stream_loading_timer = types.SimpleNamespace(stop=lambda: None)
    dw._stop_hls_playback = lambda: None
    dw.stop_current_video = lambda: None
    dw._show_stream_status = lambda text: None
    dw._play_mpv_stream = lambda url: played.append(url) or True
    dw._fallback_stream = lambda: fallback.append(True)
    monkeypatch.setattr(viewer, "stream_capabilities", lambda **kwargs: {"ready": True})
    monkeypatch.setattr(viewer.QTimer, "singleShot", lambda delay, callback: scheduled.append((delay, callback)))
    dw._retry_stream()
    scheduled[0][1]()
    assert played == [source]
    dw._retry_stream()
    dw._retry_stream()
    assert [delay for delay, callback in scheduled] == [2000, 5000]
    assert fallback == [True]
    scheduled[1][1]()  # Older attempt callback must not start another process.
    assert played == [source]
    dw._cancel_stream()
    assert dw.stream_source is None
    scheduled[0][1]()
    assert played == [source]


def test_stale_stream_marker_cannot_stop_current_watchdog():
    from echoview.streaming import RetryPolicy
    stopped = []
    dw = DisplayWindow.__new__(DisplayWindow)
    dw.running = True
    dw.current_mode = "web_page"
    dw.stream_generation = 10
    dw.stream_live = False
    dw.stream_retry = RetryPolicy()
    dw.stream_loading_timer = types.SimpleNamespace(stop=lambda: stopped.append(1))
    dw._on_stream_event(9, "playing")
    assert not stopped
    dw._on_stream_event(10, "playing_live")
    assert stopped == [1] and dw.stream_live
    dw.running = False
    dw._on_stream_event(10, "playing")
    assert stopped == [1]


def test_youtube_does_not_force_external_browser():
    dw = DisplayWindow.__new__(DisplayWindow)
    dw.disp_cfg = {"web_use_external_browser": False}
    stopped = []
    dw._stop_external_browser = lambda: stopped.append(True)
    assert dw._maybe_launch_external_browser("https://youtube.com/watch?v=abc123def45", None) is False
    assert stopped == [True]


def test_browser_inherits_actual_x11_session(monkeypatch):
    from echoview import viewer
    captures = []
    monkeypatch.setenv("DISPLAY", ":19")
    monkeypatch.setenv("XAUTHORITY", "/tmp/session-fixture")
    proc = types.SimpleNamespace(poll=lambda: None)
    monkeypatch.setattr(viewer.subprocess, "Popen", lambda cmd, **kwargs: captures.append(kwargs["env"]) or proc)
    monkeypatch.setattr(viewer.QTimer, "singleShot", lambda *args: None)
    dw = DisplayWindow.__new__(DisplayWindow)
    dw.external_browser_proc = None
    dw._stop_external_browser = lambda: None
    dw._build_chromium_command = lambda url: ["chromium", url]
    dw._start_external_browser_log_thread = lambda proc: None
    dw.foreground_label = types.SimpleNamespace(setText=lambda text: None)
    assert dw._ensure_external_browser("https://example.invalid")
    assert captures[0]["DISPLAY"] == ":19"
    assert captures[0]["XAUTHORITY"] == "/tmp/session-fixture"


def test_mpv_normal_end_and_live_end_have_distinct_behavior():
    from echoview import embed_utils
    dw = DisplayWindow.__new__(DisplayWindow)
    dw.current_mode = "web_page"
    dw.stream_source = "https://youtube.com/watch?v=abc123def45"
    dw.stream_metadata = embed_utils.classify_url(dw.stream_source)
    dw.stream_live = False
    dw.stream_loading_timer = types.SimpleNamespace(stop=lambda: None)
    dw.current_video_proc = types.SimpleNamespace(poll=lambda: 0)
    dw.stop_current_video = lambda: None
    ended, retries = [], []
    dw._show_stream_status = ended.append
    dw._retry_stream = lambda: retries.append(1)
    dw._check_mpv_process()
    assert ended == ["Playback ended."] and not retries
    dw.stream_live = True
    dw._check_mpv_process()
    assert retries == [1]
