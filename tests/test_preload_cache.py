import os, sys, types

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "echoview"))

# Provide dummy PySide6 modules
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
qtcore.QTimer = type("QTimer", (), {"singleShot": staticmethod(lambda ms, f: f())})
qtcore.Slot = lambda *a, **k: (lambda f: f)
qtcore.QSize = object
qtcore.QRect = object
qtcore.QRectF = object

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

sys.modules.setdefault("PySide6", types.ModuleType("PySide6"))
sys.modules.setdefault("PySide6.QtCore", qtcore)
sys.modules.setdefault("PySide6.QtGui", qtgui)
sys.modules.setdefault("PySide6.QtWidgets", qtwidgets)
sys.modules.setdefault("requests", types.ModuleType("requests"))
sys.modules.setdefault("psutil", types.ModuleType("psutil"))
spotipy = types.ModuleType("spotipy")
spotipy.Spotify = type("Spotify", (), {})
oauth2 = types.ModuleType("spotipy.oauth2")
oauth2.SpotifyOAuth = type("SpotifyOAuth", (), {})
spotipy.oauth2 = oauth2
sys.modules.setdefault("spotipy", spotipy)
sys.modules.setdefault("spotipy.oauth2", oauth2)

from collections import OrderedDict
from echoview.viewer import DisplayWindow


def test_preload_blurred_backgrounds():
    dw = DisplayWindow.__new__(DisplayWindow)
    dw.image_cache = OrderedDict()
    dw.bg_cache = OrderedDict()
    dw.bg_blur_radius = 5
    dw.bg_scale_percent = 100
    dw.bg_cache_capacity = 10
    dw.preload_count = 5
    dw.image_list = [f"img{i}" for i in range(6)]
    dw.index = 0

    def fake_cached_image(path):
        return {"type": "static", "pixmap": path}

    calls = []
    def fake_make_background(pm):
        calls.append(pm)
        return f"blur_{pm}"

    dw.get_cached_image = fake_cached_image
    dw.make_background_cover = fake_make_background

    # Bind method from class
    from types import MethodType
    dw.get_cached_background = MethodType(DisplayWindow.get_cached_background, dw)

    dw.preload_next_images()

    assert len(dw.bg_cache) == dw.preload_count
    expected = [f"img{i}" for i in range(1, 6)]
    assert [k[0] for k in dw.bg_cache.keys()] == expected
    assert calls == expected
