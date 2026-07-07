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
    dw.disp_cfg = {"video_category": "Cats", "shuffle_videos": False}
    dw.current_mode = "videos"
    dw.image_list = []
    dw.index = 0
    DisplayWindow.build_local_image_list(dw)
    expected = [str(folder1 / "a.mp4")]
    assert dw.image_list == expected


def test_build_mpv_command_volume(monkeypatch):
    dw = DisplayWindow.__new__(DisplayWindow)
    dw.disp_cfg = {"video_mute": False, "video_volume": 55}
    cmd = DisplayWindow.build_mpv_command(dw, "/tmp/test.mp4")
    assert "--mute=no" in cmd
    assert "--volume=55" in cmd
    assert "--keep-open=no" in cmd


def test_build_mpv_command_mute(monkeypatch):
    dw = DisplayWindow.__new__(DisplayWindow)
    dw.disp_cfg = {"video_mute": True, "video_volume": 55}
    cmd = DisplayWindow.build_mpv_command(dw, "/tmp/test.mp4")
    assert "--mute=yes" in cmd
    assert "--volume=0" in cmd
    assert "--keep-open=no" in cmd


def test_chromium_profile_dir_is_persistent(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    dw = DisplayWindow.__new__(DisplayWindow)
    dw.disp_name = "Display 1"
    dw.assigned_screen = types.SimpleNamespace(name=lambda: "HDMI-1")

    user_dir = DisplayWindow._chromium_user_data_dir(dw)

    assert user_dir == str(tmp_path / "echoview" / "chromium-Display_1-HDMI-1")
    assert not user_dir.startswith("/tmp/echoview-chromium-")


def test_build_chromium_command_uses_browser_like_flags(monkeypatch, tmp_path):
    monkeypatch.setenv("ECHOVIEW_CHROMIUM_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(DisplayWindow, "_find_chromium_binary", lambda self: "/usr/bin/chromium")

    geom = types.SimpleNamespace(x=lambda: 10, y=lambda: 20, width=lambda: 800, height=lambda: 480)
    dw = DisplayWindow.__new__(DisplayWindow)
    dw.disp_name = "Display0"
    dw.assigned_screen = types.SimpleNamespace(name=lambda: "HDMI-1", geometry=lambda: geom)

    cmd = DisplayWindow._build_chromium_command(dw, "https://youtube.com/watch?v=test")

    assert cmd is not None
    assert "--disable-gpu" in cmd
    assert "--disable-software-rasterizer" not in cmd
    assert f"--user-agent={viewer.STANDALONE_CHROMIUM_USER_AGENT}" in cmd
    assert f"--user-data-dir={tmp_path / 'chromium-Display0-HDMI-1'}" in cmd
    assert os.path.isdir(tmp_path / "chromium-Display0-HDMI-1")


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
    rect_obj = types.SimpleNamespace(width=lambda: 100, height=lambda: 100)
    dw.main_widget = types.SimpleNamespace(rect=lambda: rect_obj)
    dw.overlay_config = {}
    dw.current_pixmap = None
    dw.handling_gif_frames = False
    dw.current_movie = None
    dw.bg_label = types.SimpleNamespace(setPixmap=lambda *a, **k: None)
    DisplayWindow.stop_current_video(dw, advance=True)
    assert advanced == ["next"]


def test_next_image_starts_from_first(monkeypatch):
    dw = DisplayWindow.__new__(DisplayWindow)
    dw.running = True
    dw.current_mode = "random_image"
    dw.image_list = ["a.jpg", "b.jpg", "c.jpg"]
    dw.index = -1
    dw.image_cache = {}
    dw.last_displayed_path = None
    dw.overlay_config = {}
    dw.fallback_image_list = []
    dw.fallback_index = -1
    recorded = []
    dw.show_foreground_image = lambda path, is_spotify=False: recorded.append(path)
    dw.prefetch_next_image = lambda: None
    dw.clock_label = types.SimpleNamespace(update=lambda: None)

    dw.next_image(force=True)
    assert recorded == ["a.jpg"]
    assert dw.index == 0
    assert dw.last_displayed_path == "a.jpg"

    dw.next_image()
    assert recorded[-1] == "b.jpg"
    assert dw.index == 1


def test_ignored_folder_not_loaded(monkeypatch, tmp_path):
    # Prepare folders
    photos = tmp_path / "Photos"
    photos.mkdir()
    (photos / "a.jpg").write_text("x")
    hidden = tmp_path / "_ai_temp"
    hidden.mkdir()
    (hidden / "b.jpg").write_text("x")

    monkeypatch.setattr(viewer, "IMAGE_DIR", str(tmp_path))
    dw = DisplayWindow.__new__(DisplayWindow)
    dw.disp_cfg = {
        "mode": "random_image",
        "image_category": "_ai_temp",
        "shuffle_mode": False,
        "mixed_folders": [],
        "video_category": "",
        "shuffle_videos": False,
    }
    dw.current_mode = "random_image"
    dw.image_list = []
    dw.fallback_image_list = []
    dw.cache_lock = viewer.threading.Lock()

    # Hidden folder is ignored, leaving no images
    dw.build_local_image_list()
    assert dw.image_list == []

    # Mixed folders should filter hidden entries
    dw.current_mode = "mixed"
    dw.disp_cfg["mixed_folders"] = ["_ai_temp", "Photos"]
    dw.build_local_image_list()
    assert dw.image_list == [str(photos / "a.jpg")]


def test_maybe_launch_external_browser_honors_web_toggle():
    dw = DisplayWindow.__new__(DisplayWindow)
    dw.disp_cfg = {"web_use_external_browser": True}
    events = []
    dw._stop_hls_playback = lambda: events.append("stop_hls")
    dw.web_view = types.SimpleNamespace(hide=lambda: events.append("hide_web"))
    dw.stop_current_video = lambda: events.append("stop_video")
    dw._ensure_external_browser = lambda url: events.append(("launch", url)) or True
    dw._stop_external_browser = lambda: events.append("stop_external")

    result = DisplayWindow._maybe_launch_external_browser(
        dw,
        "https://example.com/page-with-youtube",
        None,
    )

    assert result is True
    assert events == [
        "stop_hls",
        "hide_web",
        "stop_video",
        ("launch", "https://example.com/page-with-youtube"),
    ]
