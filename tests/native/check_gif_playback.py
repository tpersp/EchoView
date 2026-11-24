"""Run separately with real runtime dependencies; no network or device settings.

    QT_QPA_PLATFORM=offscreen python tests/native/check_gif_playback.py

Restricted containers may also require QTWEBENGINE_DISABLE_SANDBOX=1.
"""
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import time


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
        cached = window.image_cache[str(fixture)]
        assert cached['encoded'] is not None
        assert cached['bytes'] == cached['image'].sizeInBytes() + fixture.stat().st_size
        assert movie.device() is not None and movie.fileName() == ''
        # Animation must survive cache eviction and source removal. Only this
        # temporary synthetic file is deleted; never use real media in the test.
        window.image_cache.clear()
        fixture.unlink()
        assert movie.speed() == 100 and movie.loopCount() == -1
        events, colours = [], set()

        def frame_changed(index):
            events.append(index)
            colours.add(movie.currentImage().pixelColor(0, 0).name())

        movie.frameChanged.connect(frame_changed)
        deadline_checks=[]
        def check_live_deadline():
            try:
                window.diagnostics.close()
                window.diagnostics.thread.join(timeout=1)
                while not window.diagnostics.messages.empty():window.diagnostics.messages.get_nowait()
                window.diag_gif_frames=2
                window.diag_gif_due=time.monotonic()+10
                window._diagnostic_snapshot()
                assert window.diagnostics.messages.empty(), 'Long GIF frames are intentional'
                window.diag_gif_due=time.monotonic()-3
                window._diagnostic_snapshot()
                category,detail=window.diagnostics.messages.get_nowait()
                assert category=='gif-frame-delayed' and 'live frame deadline' in detail
                deadline_checks.append(True)
            except Exception as exc:deadline_checks.append(exc)
        QTimer.singleShot(1000, check_live_deadline)
        QTimer.singleShot(1400, app.quit)
        app.exec()
        assert deadline_checks==[True],deadline_checks
        assert {0, 1, 2} <= set(events) and len(events) >= 6, (profile, rotation, events)
        assert colours == {'#ff0000', '#008000', '#0000ff'}, colours
        assert movie.speed() == 100
        window.close()
        app.processEvents()
        print(f'{profile}, rotation {rotation}: looping GIF advances with normal playback speed ({len(events)} frames).')


if __name__ == '__main__':
    main()
