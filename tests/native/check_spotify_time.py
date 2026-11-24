"""Native timing toggle/layout checks using injected playback, no API or NAS."""
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
with tempfile.TemporaryDirectory(prefix='echoview-spotify-time-') as directory:
    os.environ['VIEWER_HOME'] = os.environ['IMAGE_DIR'] = directory
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PIL import Image
    from PySide6.QtWidgets import QApplication
    from echoview import viewer
    from echoview.spotify_client import Playback
    app = QApplication([])
    display = {'mode': 'calibration', 'fallback_mode': 'none'}
    viewer.load_config = lambda: {'displays': {'fixture': display}}
    window = viewer.DisplayWindow('fixture', display, app.primaryScreen())
    now = [100.0]
    viewer.time = SimpleNamespace(monotonic=lambda: now[0])
    art = Path(directory) / 'art.png'
    Image.new('RGB', (64, 64), 'teal').save(art)
    identity = window.winId()
    window.current_mode = 'spotify'
    for layout in ('classic', 'album_card', 'poster'):
        now[0] = 100
        window.disp_cfg.update(spotify_layout=layout, spotify_show_time=True, spotify_show_progress=False)
        window.spotify_fetch_id = window.spotify_fetch_pending = 1
        window.handle_spotify_result(1, Playback('playing', song='Fixture', art_path=str(art),
            progress_ms=24000, duration_ms=194000, fetched_time=100, next_poll_at=160))
        app.processEvents()
        bar = window.spotify_progress_bar
        assert bar.isVisible() and bar._time_text == '0:24/3:14'
        assert not bar._bar_visible and bar.height() > 10
        assert window.spotify_progress_timer.interval() >= 1000
        assert window.presentation_rect().contains(bar.geometry())
        assert not bar.grab().isNull()
        now[0] = 101.2
        window.update_spotify_progress()
        assert bar._time_text == '0:25/3:14'
        timeline = window.spotify_timeline
        window.apply_spotify_visual_settings(dict(window.disp_cfg, spotify_show_progress=True))
        assert bar._bar_visible and bar._time_text == '0:25/3:14'
        assert window.spotify_timeline is timeline and window.winId() == identity
        for theme in bar.THEMES:
            bar.setTheme(theme)
            assert not bar.grab().isNull()
        window.apply_spotify_visual_settings(dict(window.disp_cfg, spotify_show_time=False))
        assert bar.isVisible() and bar._time_text == '' and bar.height() == 10
    window.apply_spotify_visual_settings(dict(window.disp_cfg, spotify_show_time=True))
    window.spotify_fetch_id = window.spotify_fetch_pending = 2
    window.handle_spotify_result(2, Playback('paused', next_poll_at=160))
    assert not window.spotify_progress_bar.isVisible() and not window.spotify_progress_timer.isActive()
    window.close()
    print('Spotify time: all layouts/themes, local clock, independent toggle, live apply and paused cleanup passed.')
