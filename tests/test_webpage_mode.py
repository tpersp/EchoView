import sys, os, types
import types

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "echoview"))

# Dummy Qt modules
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
qtcore.QTimer = type("QTimer", (), {"__init__":lambda self,*a,**k:None,"timeout":lambda self:None,"connect":lambda self,f:None,"start":lambda self,*a,**k:None,"stop":lambda self:None})
qtcore.Slot = lambda *a, **k: (lambda f: f)
qtcore.QSize = object
qtcore.QRect = object
qtcore.QRectF = object
qtcore.QUrl = lambda url: url

qtgui = types.ModuleType("PySide6.QtGui")
for name in ["QPixmap", "QMovie", "QPainter", "QImage", "QImageReader", "QTransform", "QFont"]:
    setattr(qtgui, name, type(name, (), {}))

qtwidgets = types.ModuleType("PySide6.QtWidgets")
for name in ["QApplication","QMainWindow","QWidget","QLabel","QProgressBar","QGraphicsScene","QGraphicsPixmapItem","QGraphicsBlurEffect","QSizePolicy"]:
    setattr(qtwidgets, name, type(name, (), {}))

qweb = types.ModuleType("PySide6.QtWebEngineWidgets")
class DummyWeb:
    def __init__(self, *a, **k):
        self.loaded = None
        self.shown = False
        self.hidden = False
    def load(self, url):
        self.loaded = url
    def show(self):
        self.shown = True
    def hide(self):
        self.hidden = True
    def setGeometry(self, *a):
        pass
qweb.QWebEngineView = DummyWeb

sys.modules.setdefault("PySide6", types.ModuleType("PySide6"))
sys.modules.setdefault("PySide6.QtCore", qtcore)
sys.modules.setdefault("PySide6.QtGui", qtgui)
sys.modules.setdefault("PySide6.QtWidgets", qtwidgets)
sys.modules.setdefault("PySide6.QtWebEngineWidgets", qweb)

import echoview
DisplayWindow = echoview.DisplayWindow


def test_webpage_mode_loads_url():
    dw = DisplayWindow.__new__(DisplayWindow)
    dw.running = True
    dw.main_widget = type("MW", (), {"rect": lambda self: type("R", (), {"width": lambda self:0,"height":lambda self:0})()})()
    dummy_label = type("Lbl", (), {"hide": lambda self:None})()
    dw.bg_label = dummy_label
    dw.foreground_label = dummy_label
    dw.spotify_info_label = dummy_label
    dw.spotify_progress_bar = dummy_label
    dw.disp_cfg = {"web_url": "http://example.com"}
    dw.current_mode = "webpage"
    dw.web_view = None
    dw.image_list = []
    dw.clear_foreground_label = lambda msg: None
    dw.setup_layout = lambda: None
    dw.next_image(force=True)
    assert dw.web_view.loaded == "http://example.com"
    assert dw.web_view.shown
