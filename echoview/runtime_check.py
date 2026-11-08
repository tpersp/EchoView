"""Fail-fast runtime validation; safe to run before installer mutations."""
import argparse
import platform
import sys


def compatibility_errors(system, architecture, python_version, glibc, os_info, installer=False):
    errors = []
    if system != "Linux":
        errors.append("The packaged runtime requires Linux.")
    if architecture not in ("aarch64", "x86_64"):
        errors.append("Use a 64-bit aarch64 or x86_64 OS; ARM 32-bit wheels are unavailable.")
    if not (3, 11) <= tuple(python_version[:2]) < (3, 14):
        errors.append("The selected runtime requires Python 3.11–3.13.")
    minimum = (2, 39) if architecture == "aarch64" else (2, 34)
    if tuple(glibc) < minimum:
        errors.append(f"PySide6 wheels require glibc {minimum[0]}.{minimum[1]}+ on {architecture}. Bookworm ARM64 is incompatible; use Raspberry Pi OS Trixie 64-bit.")
    if installer and (architecture != "aarch64" or os_info.get("ID") not in ("debian", "raspbian")
                      or os_info.get("VERSION_CODENAME") != "trixie"):
        errors.append("Automated setup targets Raspberry Pi OS Trixie 64-bit (Debian 13), with X11. Other hosts may run development checks, not this installer.")
    return errors


def check_qt():
    # Import only: no QApplication, display server, token or user config needed.
    from PySide6.QtCore import qVersion
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput  # noqa: F401
    from PySide6.QtMultimediaWidgets import QVideoWidget  # noqa: F401
    from PySide6.QtWebEngineCore import QWebEngineSettings  # noqa: F401
    from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
    print(f"Qt {qVersion()}: Multimedia and WebEngine imports passed.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installer", action="store_true", help="Check the automated Raspberry Pi installation target")
    parser.add_argument("--qt", action="store_true", help="Also verify native Qt module imports")
    args = parser.parse_args(argv)
    libc, version = platform.libc_ver()
    try:
        glibc = tuple(int(part) for part in version.split(".")[:2]) if libc == "glibc" else ()
    except ValueError:
        glibc = ()
    try:
        os_info = platform.freedesktop_os_release()
    except OSError:
        os_info = {}
    errors = compatibility_errors(platform.system(), platform.machine(), sys.version_info, glibc, os_info, args.installer)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("OS architecture, Python and glibc checks passed.")
    if args.qt:
        try:
            check_qt()
        except (ImportError, OSError) as exc:
            print(f"ERROR: Qt native imports failed ({exc}). Use matched packages; do not create library ABI symlinks.", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
