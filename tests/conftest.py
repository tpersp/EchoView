import sys
import types


sys.modules.setdefault("PySide6", types.ModuleType("PySide6"))

if "PySide6.QtWebEngineCore" not in sys.modules:
    qtwebengine_core = types.ModuleType("PySide6.QtWebEngineCore")
    qtwebengine_core.QWebEngineSettings = type(
        "QWebEngineSettings",
        (),
        {
            "PlaybackRequiresUserGesture": object(),
            "defaultSettings": staticmethod(
                lambda: types.SimpleNamespace(setAttribute=lambda *args, **kwargs: None)
            ),
            "globalSettings": staticmethod(
                lambda: types.SimpleNamespace(setAttribute=lambda *args, **kwargs: None)
            ),
        },
    )
    sys.modules["PySide6.QtWebEngineCore"] = qtwebengine_core
