"""Real Qt: slow file checks/decodes do not pause existing media or timers.

Run offscreen in an externally time-limited subprocess. All media is synthetic.
"""
import os
from pathlib import Path
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
with tempfile.TemporaryDirectory(prefix='echoview-async-images-') as directory:
    os.environ['VIEWER_HOME'] = os.environ['IMAGE_DIR'] = directory
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PIL import Image
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from echoview import viewer

    app = QApplication([])
    display = {'mode': 'calibration'}
    cfg = {'displays': {'fixture': display}}
    viewer.load_config = lambda: cfg
    window = viewer.DisplayWindow('fixture', display, app.primaryScreen())
    root = Path(directory)
    gif, cached, cold = root / 'playing.gif', root / 'cached.png', root / 'cold.png'
    frames = [Image.new('RGB', (64, 48), c) for c in ('red', 'blue')]
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=60, loop=0)
    frames[0].save(cached)
    frames[1].save(cold)
    window.get_cached_image(str(cached))
    beats, frame_events = [], []
    timer = QTimer()
    timer.timeout.connect(lambda: beats.append(time.monotonic()))
    timer.start(20)

    def wait_for(predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.003)
        assert predicate(), 'Timed out waiting for asynchronous image operation'

    original_exists = viewer.os.path.exists
    original_load = window.load_and_cache_image
    main_thread = threading.get_ident()
    for slow_check in (True, False):
        window.show_foreground_image(str(gif))
        movie = window.current_movie
        movie.frameChanged.connect(lambda _: frame_events.append(1))
        started, release = threading.Event(), threading.Event()
        target = str(cached if slow_check else cold)
        threads = []

        def blocked():
            threads.append(threading.get_ident())
            started.set()
            assert release.wait(2)

        def exists(path):
            if path == target:
                blocked()
            return original_exists(path)

        def load(path):
            if path == target:
                blocked()
            return original_load(path)

        if slow_check:
            viewer.os.path.exists = exists
        else:
            window.load_and_cache_image = load
        before, frames_before = len(beats), len(frame_events)
        window.request_foreground_image(target)
        wait_for(started.is_set)
        QTimer.singleShot(350, release.set)
        wait_for(release.is_set)
        assert threads == [window.image_loader.thread.ident] and threads[0] != main_thread
        assert len(beats) - before >= 10 and len(frame_events) > frames_before
        wait_for(lambda: window.current_movie is None)
        assert window.current_pixmap is not None
        viewer.os.path.exists = original_exists
        window.load_and_cache_image = original_load

    # A deleted source is still reported missing even if its pixels are cached.
    cached.unlink()
    window.request_foreground_image(str(cached))
    wait_for(lambda: window.foreground_label.text() == 'Missing file')
    assert window.current_pixmap is None

    # Late completion must not replace a new mode's display.
    started, release = threading.Event(), threading.Event()
    target = str(cold)
    viewer.os.path.exists = exists
    window.request_foreground_image(target)
    wait_for(started.is_set)
    window.reload_settings(cfg)
    window.next_image(force=True)
    calibration = window.current_pixmap.cacheKey()
    release.set()
    deadline = time.monotonic() + .2
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.003)
    assert window.current_pixmap.cacheKey() == calibration
    viewer.os.path.exists = original_exists
    window.close()
    print('Async images: cached slow stat and cold slow decode keep GIF/timers moving; missing cached source and stale-mode completion handled.')
