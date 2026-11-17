"""Real Qt schedule transitions using only temporary media and an injected clock.

    QT_QPA_PLATFORM=offscreen python tests/native/check_schedule.py

Images/GIFs decode normally; video selection is checked without launching mpv.
"""
from copy import deepcopy
from datetime import datetime
import os
from pathlib import Path
import sys
import tempfile


def main():
    with tempfile.TemporaryDirectory(prefix='echoview-schedule-') as temp:
        os.environ['VIEWER_HOME'] = temp
        os.environ['IMAGE_DIR'] = temp
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from PIL import Image
        from PySide6.QtWidgets import QApplication
        from echoview import viewer

        class Clock:
            value = datetime(2026, 11, 18, 7)
            @classmethod
            def now(cls): return cls.value
        viewer.datetime = Clock
        root = Path(temp)
        for name in ('Morning', 'Afternoon', 'Evening A', 'Evening B'):
            (root / name).mkdir()
        frames = [Image.new('RGB', (64, 48), colour) for colour in ('red', 'green')]
        frames[0].save(root / 'Morning' / 'animation.gif', save_all=True, append_images=frames[1:], duration=100, loop=0)
        frames[1].save(root / 'Afternoon' / 'photo.png')
        for name in ('Evening A', 'Evening B'):
            (root / name / 'clip.mp4').touch()
        display = {'mode': 'scheduled', 'image_interval': 60, 'schedule': [
            {'time': '06:00', 'folders': ['Morning']},
            {'time': '14:00', 'folders': ['Afternoon']},
            {'time': '18:00', 'folders': ['Evening A', 'Evening B'], 'media': 'videos'},
        ]}
        cfg = {'resource_profile': 'standard', 'displays': {'fixture': display}}
        before = deepcopy(cfg)
        viewer.load_config = lambda: cfg
        app = QApplication([])
        window = viewer.DisplayWindow('fixture', display, app.primaryScreen())
        app.processEvents()
        identity = window.winId()
        assert window.current_mode == 'mixed' and window.current_movie is not None
        assert window.last_displayed_path.endswith('animation.gif')
        Clock.value = datetime(2026, 11, 18, 14)
        window._check_schedule()
        assert window.current_movie is None
        assert window.last_displayed_path.endswith('photo.png')
        assert window.winId() == identity
        generation = window.cache_generation
        window._check_schedule()
        assert window.cache_generation == generation
        selected = []
        window.play_next_video = lambda: selected.extend(window.image_list)
        Clock.value = datetime(2026, 11, 18, 18)
        window._check_schedule()
        assert window.current_mode == 'videos'
        assert set(selected) == {str(root / name / 'clip.mp4') for name in ('Evening A', 'Evening B')}
        assert cfg == before
        display['schedule'] = [{'time': '00:00', 'folders': ['Recovering']}]
        window.reload_settings(cfg)
        window.next_image(force=True)
        assert not window.image_list
        (root / 'Recovering').mkdir()
        frames[0].save(root / 'Recovering' / 'returned.png')
        window.schedule_retry_due = 0
        window._check_schedule()
        assert window.last_displayed_path.endswith('returned.png')
        window.close()
        assert not window.schedule_timer.isActive()
        app.processEvents()
        print('Real Qt schedule passed: GIF → image → grouped video selection, stable window, no repeated switching, media recovery and timer cleanup. No NAS media or live playback was touched.')


if __name__ == '__main__':
    main()
