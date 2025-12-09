import os
import sys
import types

import pytest

if "psutil" not in sys.modules:
    dummy_psutil = types.ModuleType("psutil")
    dummy_psutil.cpu_percent = lambda interval=0: 0
    dummy_psutil.virtual_memory = lambda: types.SimpleNamespace(total=0, available=0)
    sys.modules["psutil"] = dummy_psutil

# Stub PySide6/spotipy for headless test environment
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
    def __init__(self, *a, **k):
        pass
    def start(self, *a, **k):
        pass
    def stop(self, *a, **k):
        pass
    def setInterval(self, *a, **k):
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
qtwidgets.QApplication = type("QApplication", (), {"screens": staticmethod(lambda: [])})
for name in [
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
sys.modules.setdefault("PySide6.QtWebEngineWidgets", qtweb)
sys.modules.setdefault("PySide6.QtMultimedia", qtmultimedia)
sys.modules.setdefault("PySide6.QtMultimediaWidgets", qtmultimedia_widgets)
sys.modules.setdefault("spotipy", spotipy)
sys.modules.setdefault("spotipy.oauth2", oauth2)

try:
    from PIL import Image
except ImportError:
    Image = None

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "echoview"))

from echoview import utils, viewer  # noqa: E402


def _make_image(path, size):
    img = Image.new("RGB", size, color=(255, 0, 0))
    img.save(path)


@pytest.mark.skipif(Image is None, reason="Pillow not installed")
def test_media_aspect_label_images(tmp_path):
    square = tmp_path / "sq.png"
    landscape = tmp_path / "land.png"
    portrait = tmp_path / "port.png"
    _make_image(square, (100, 100))
    _make_image(landscape, (160, 90))
    _make_image(portrait, (90, 160))

    assert utils.media_aspect_label(square) == "square"
    assert utils.media_aspect_label(landscape) == "landscape"
    assert utils.media_aspect_label(portrait) == "portrait"


def test_filter_by_aspect_uses_cache(monkeypatch):
    dw = viewer.DisplayWindow.__new__(viewer.DisplayWindow)
    dw.disp_cfg = {"aspect_filter": "square"}
    dw.aspect_cache = {}

    labels = {
        "/tmp/a.jpg": "square",
        "/tmp/b.jpg": "landscape",
        "/tmp/c.jpg": "portrait",
    }

    monkeypatch.setattr(viewer, "media_aspect_label", lambda p: labels.get(p, "unknown"))

    result = viewer.DisplayWindow._filter_by_aspect(dw, list(labels.keys()))
    assert result == ["/tmp/a.jpg"]
    # Second call should hit cache and produce same result
    result2 = viewer.DisplayWindow._filter_by_aspect(dw, list(labels.keys()))
    assert result2 == result
