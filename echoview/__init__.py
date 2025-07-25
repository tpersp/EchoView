"""EchoView package initialization with lazy imports."""

def create_app():
    from echoview.web.app import create_app as _create_app
    return _create_app()

def __getattr__(name):
    if name == "DisplayWindow":
        from echoview.viewer import DisplayWindow
        return DisplayWindow
    raise AttributeError(f"module 'echoview' has no attribute {name}")
