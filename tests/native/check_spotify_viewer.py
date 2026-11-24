"""Exercise real viewer integration with injected Spotify samples, no network."""
from pathlib import Path
import os
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
with tempfile.TemporaryDirectory(prefix='echoview-spotify-viewer-') as directory:
    os.environ['VIEWER_HOME'] = directory
    os.environ['IMAGE_DIR'] = directory
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from echoview import viewer
    from echoview.spotify_client import Playback
    display = dict(mode='calibration', spotify_show_progress=True, fallback_mode='none')
    cfg = {'displays': {'fixture': display}, 'resource_profile': 'standard'}
    viewer.load_config = lambda: cfg
    app = QApplication([])
    window = viewer.DisplayWindow('fixture', display, app.primaryScreen())
    window.current_mode = 'spotify'
    window.spotify_fetch_id = window.spotify_fetch_pending = 1
    window.handle_spotify_result(1, Playback('playing', track_id='test-track', song='Fixture',
                                 progress_ms=18000, duration_ms=180000, fetched_time=time.monotonic(),
                                 next_poll_at=time.monotonic()+60))
    assert window.spotify_progress_timer.interval() == 50
    values = []
    for _ in range(8):
        app.processEvents()
        values.append(window.spotify_progress_bar.value())
        time.sleep(.05)
    assert values[-1] > values[0], values
    window.disp_cfg['spotify_smooth_progress'] = False
    window.render_spotify('')
    assert window.spotify_progress_timer.interval() == 200
    window.disp_cfg['spotify_smooth_progress'] = True
    window.resource_options['progress_interval'] = 500
    window.render_spotify('')
    assert window.spotify_progress_timer.interval() == 500
    window.spotify_fetch_id = window.spotify_fetch_pending = 2
    window.handle_spotify_result(2, Playback('paused', next_poll_at=time.monotonic()+60))
    assert window.spotify_timeline.position(time.monotonic()) == 0
    assert not window.spotify_progress_timer.isActive()
    window.close()
    app.processEvents()
    print('Real viewer Spotify: animated progress, legacy interval, low-resource cap and pause cleanup passed.')
