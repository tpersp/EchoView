"""Run separately with real runtime dependencies; no network or device settings.

    QT_QPA_PLATFORM=offscreen python tests/native/check_gif_playback.py

Restricted containers may also require QTWEBENGINE_DISABLE_SANDBOX=1.
"""
import os
from pathlib import Path
import sys
import subprocess
import tempfile


def main():
    if len(sys.argv) == 1:
        # Separate GUI lifetimes keep each native playback check independent.
        for profile in ('standard', 'pi3'):
            for rotation in (0, 90):
                subprocess.run([sys.executable, str(Path(__file__).resolve()), profile, str(rotation)], check=True)
        return
    profile, rotation = sys.argv[1], int(sys.argv[2])
    with tempfile.TemporaryDirectory(prefix='echoview-gif-check-') as temp:
        os.environ['VIEWER_HOME'] = temp
        os.environ['IMAGE_DIR'] = temp
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from PIL import Image
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        from echoview import viewer

        fixture = Path(temp) / 'animation.gif'
        images = [Image.new('RGB', (64, 48), colour) for colour in ('red', 'green', 'blue')]
        images[0].save(fixture, save_all=True, append_images=images[1:], duration=[80, 120, 160], loop=0)
        app = QApplication([])
        app.setQuitOnLastWindowClosed(False)
        display = {'mode': 'calibration', 'rotate': rotation}
        cfg = {'resource_profile': profile, 'displays': {'fixture': display},
               'gui': {'foreground_scale_percent': 75 if rotation else 100}}
        viewer.load_config = lambda: cfg
        window = viewer.DisplayWindow('fixture', display, app.primaryScreen())
        window.show_foreground_image(str(fixture))
        movie = window.current_movie
        assert movie is not None, (profile, rotation, 'GIF animation missing')
        assert movie.speed() == 100 and movie.loopCount() == -1
        events, colours = [], set()

        def frame_changed(index):
            events.append(index)
            colours.add(movie.currentImage().pixelColor(0, 0).name())

        movie.frameChanged.connect(frame_changed)
        QTimer.singleShot(1400, app.quit)
        app.exec()
        assert {0, 1, 2} <= set(events) and len(events) >= 6, (profile, rotation, events)
        assert colours == {'#ff0000', '#008000', '#0000ff'}, colours
        assert movie.speed() == 100
        window.close()
        app.processEvents()
        print(f'{profile}, rotation {rotation}: looping GIF advances with normal playback speed ({len(events)} frames).')


if __name__ == '__main__':
    main()
