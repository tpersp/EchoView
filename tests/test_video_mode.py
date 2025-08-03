import os, sys, types, random

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "echoview"))

# Stub PySide6 modules
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
    def start(self):
        pass
    def stop(self):
        pass
    def setInterval(self, *a):
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
sys.modules.setdefault("spotipy", spotipy)
sys.modules.setdefault("spotipy.oauth2", oauth2)

import echoview.viewer as viewer
DisplayWindow = viewer.DisplayWindow


def test_build_video_list(tmp_path, monkeypatch):
    folder1 = tmp_path / "Cats"
    folder1.mkdir()
    (folder1 / "a.mp4").write_text("vid")
    (folder1 / "b.jpg").write_text("img")
    folder2 = tmp_path / "Dogs"
    folder2.mkdir()
    (folder2 / "c.webm").write_text("vid")
    monkeypatch.setattr(viewer, "IMAGE_DIR", str(tmp_path))
    dw = DisplayWindow.__new__(DisplayWindow)
    dw.disp_cfg = {"video_folders": ["Cats", "Dogs"], "shuffle_videos": False}
    dw.current_mode = "videos"
    dw.image_list = []
    dw.index = 0
    DisplayWindow.build_local_image_list(dw)
    expected = [str(folder1 / "a.mp4"), str(folder2 / "c.webm")]
    assert dw.image_list == expected


def test_build_mpv_command_volume(monkeypatch):
    dw = DisplayWindow.__new__(DisplayWindow)
    dw.disp_cfg = {"video_mute": False, "video_volume": 55}
    cmd = DisplayWindow.build_mpv_command(dw, "/tmp/test.mp4")
    assert "--mute=no" in cmd
    assert "--volume=55" in cmd


def test_build_mpv_command_mute(monkeypatch):
    dw = DisplayWindow.__new__(DisplayWindow)
    dw.disp_cfg = {"video_mute": True, "video_volume": 55}
    cmd = DisplayWindow.build_mpv_command(dw, "/tmp/test.mp4")
    assert "--mute=yes" in cmd
    assert "--volume=0" in cmd


def test_play_next_video_sequential(monkeypatch):
    dw = DisplayWindow.__new__(DisplayWindow)
    dw.disp_cfg = {"video_play_to_end": True}
    dw.image_list = ["a.mp4", "b.mp4"]
    dw.index = 0
    dw.current_video_proc = None

    played = []

    def fake_build(self, path):
        played.append(path)
        return ["echo", path]

    monkeypatch.setattr(DisplayWindow, "build_mpv_command", fake_build)

    class DummyProc:
        def wait(self):
            pass

        def poll(self):
            return 0

        def terminate(self):
            pass

    monkeypatch.setattr(viewer.subprocess, "Popen", lambda cmd: DummyProc())
    monkeypatch.setattr(viewer.shutil, "which", lambda x: True)
    monkeypatch.setattr(viewer.threading, "Thread", lambda *a, **k: types.SimpleNamespace(start=lambda: None))

    dw.play_next_video()

    assert played == ["a.mp4"]
    assert dw.index == 1


def test_stop_current_video_advances(monkeypatch):
    dw = DisplayWindow.__new__(DisplayWindow)
    dummy_proc = types.SimpleNamespace(poll=lambda: 0)
    dw.current_video_proc = dummy_proc
    advanced = []
    dw.next_image = lambda force=False: advanced.append("next")
    dw.spotify_progress_bar = types.SimpleNamespace(isVisible=lambda: False)
    dw.disp_cfg = {}
    dw.spotify_info_label = types.SimpleNamespace(x=lambda: 0, y=lambda: 0, width=lambda: 0, height=lambda: 0)
    dw.clock_label = types.SimpleNamespace(isVisible=lambda: False)
    dw.overlay_config = {}
    dw.current_pixmap = None
    dw.handling_gif_frames = False
    dw.current_movie = None
    dw.bg_label = types.SimpleNamespace(setPixmap=lambda *a, **k: None)
    DisplayWindow.stop_current_video(dw, advance=True)
    assert advanced == ["next"]
