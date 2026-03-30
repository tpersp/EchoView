import os
import sys
import types
from urllib.parse import parse_qs, urlparse


REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "echoview"))


qtcore = types.ModuleType("PySide6.QtCore")


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
    def __init__(self, *args, **kwargs):
        pass

    def start(self, *args, **kwargs):
        pass

    def stop(self, *args, **kwargs):
        pass

    def setInterval(self, *args, **kwargs):
        pass

    @staticmethod
    def singleShot(ms, func):
        func()


qtcore.QTimer = DummyTimer
qtcore.Slot = lambda *args, **kwargs: (lambda func: func)
qtcore.QSize = object
qtcore.QRect = object
qtcore.QRectF = object
qtcore.QUrl = object

qtgui = types.ModuleType("PySide6.QtGui")
for name in ["QPixmap", "QMovie", "QPainter", "QImage", "QImageReader", "QTransform", "QFont"]:
    setattr(qtgui, name, type(name, (), {}))

qtwidgets = types.ModuleType("PySide6.QtWidgets")
qtwidgets.QApplication = type("QApplication", (), {"screens": staticmethod(lambda: [])})
for name in [
    "QMainWindow",
    "QWidget",
    "QLabel",
    "QProgressBar",
    "QGraphicsScene",
    "QGraphicsPixmapItem",
    "QGraphicsBlurEffect",
]:
    setattr(qtwidgets, name, type(name, (), {}))

qtwebengine_core = types.ModuleType("PySide6.QtWebEngineCore")
qtwebengine_core.QWebEngineSettings = type(
    "QWebEngineSettings",
    (),
    {
        "PlaybackRequiresUserGesture": object(),
        "defaultSettings": staticmethod(lambda: types.SimpleNamespace(setAttribute=lambda *args, **kwargs: None)),
    },
)

qtwebengine_widgets = types.ModuleType("PySide6.QtWebEngineWidgets")
qtwebengine_widgets.QWebEngineView = type("QWebEngineView", (), {})

qtmultimedia = types.ModuleType("PySide6.QtMultimedia")
qtmultimedia.QAudioOutput = type("QAudioOutput", (), {})
qtmultimedia.QMediaPlayer = type("QMediaPlayer", (), {})

qtmultimedia_widgets = types.ModuleType("PySide6.QtMultimediaWidgets")
qtmultimedia_widgets.QVideoWidget = type("QVideoWidget", (), {})

spotipy = types.ModuleType("spotipy")
spotipy.Spotify = type("Spotify", (), {})
oauth2 = types.ModuleType("spotipy.oauth2")
oauth2.SpotifyOAuth = type("SpotifyOAuth", (), {})
spotipy.oauth2 = oauth2

sys.modules.setdefault("PySide6", types.ModuleType("PySide6"))
sys.modules.setdefault("PySide6.QtCore", qtcore)
sys.modules.setdefault("PySide6.QtGui", qtgui)
sys.modules.setdefault("PySide6.QtWidgets", qtwidgets)
sys.modules.setdefault("PySide6.QtWebEngineCore", qtwebengine_core)
sys.modules.setdefault("PySide6.QtWebEngineWidgets", qtwebengine_widgets)
sys.modules.setdefault("PySide6.QtMultimedia", qtmultimedia)
sys.modules.setdefault("PySide6.QtMultimediaWidgets", qtmultimedia_widgets)
sys.modules.setdefault("spotipy", spotipy)
sys.modules.setdefault("spotipy.oauth2", oauth2)

from echoview import embed_utils, viewer


def test_build_youtube_embed_url_applies_user_preferences():
    window = viewer.DisplayWindow.__new__(viewer.DisplayWindow)
    window.disp_cfg = {
        "youtube_autoplay": False,
        "youtube_mute": False,
        "youtube_captions": True,
        "youtube_quality": "hd1080",
        "web_url": "",
    }
    metadata = embed_utils.EmbedMetadata(
        embed_type="youtube",
        original_url="https://www.youtube.com/watch?v=abc123def45",
        canonical_url="https://www.youtube-nocookie.com/embed/abc123def45?start=90",
        content_type="video",
    )

    result = viewer.DisplayWindow._build_youtube_embed_url(window, metadata)
    parsed = urlparse(result)
    query = parse_qs(parsed.query)

    assert parsed.netloc == "www.youtube-nocookie.com"
    assert query["autoplay"] == ["0"]
    assert query["mute"] == ["0"]
    assert query["cc_load_policy"] == ["1"]
    assert query["vq"] == ["hd1080"]
    assert query["playsinline"] == ["1"]
    assert query["rel"] == ["0"]
    assert query["modestbranding"] == ["1"]
    assert query["enablejsapi"] == ["1"]
    assert query["feature"] == ["oembed"]
    assert query["origin"] == ["https://echoview.local"]
    assert query["start"] == ["90"]


def test_build_youtube_embed_url_for_live_strips_playlist_and_start_params():
    window = viewer.DisplayWindow.__new__(viewer.DisplayWindow)
    window.disp_cfg = {
        "youtube_autoplay": True,
        "youtube_mute": True,
        "youtube_captions": False,
        "youtube_quality": "default",
        "web_url": "",
    }
    metadata = embed_utils.EmbedMetadata(
        embed_type="youtube",
        original_url="https://www.youtube.com/watch?v=live123abcdE",
        canonical_url=(
            "https://www.youtube.com/embed/live_stream"
            "?channel=UC123&list=PL999&index=2&start=30&feature=oembed"
        ),
        content_type="live",
    )

    result = viewer.DisplayWindow._build_youtube_embed_url(window, metadata)
    query = parse_qs(urlparse(result).query)

    assert query["autoplay"] == ["1"]
    assert query["mute"] == ["1"]
    assert "cc_load_policy" not in query
    assert "vq" not in query
    assert "list" not in query
    assert "index" not in query
    assert "start" not in query
    assert "feature" not in query
    assert query["channel"] == ["UC123"]
    assert query["origin"] == ["https://echoview.local"]
