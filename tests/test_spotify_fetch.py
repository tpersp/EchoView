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
