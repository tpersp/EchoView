"""Browser defaults use the installed engine's identity and GPU capabilities."""
import os
import shlex

DEFAULT_QT_FLAGS = "--autoplay-policy=no-user-gesture-required"
LEGACY_QT_FLAGS = (
    "--no-sandbox --disable-gpu --autoplay-policy=no-user-gesture-required "
    "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def qt_flags(value):
    # Replace the exact historical shipped default, preserving custom overrides.
    return DEFAULT_QT_FLAGS if value is None or value == LEGACY_QT_FLAGS else value


def chromium_flags():
    return shlex.split(os.environ.get("ECHOVIEW_CHROMIUM_FLAGS", ""))
