"""Synthetic viewer frame previews; no live configuration, media or services.

Run under QT_QPA_PLATFORM=offscreen with an external timeout.
"""
from io import BytesIO
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
with tempfile.TemporaryDirectory(prefix='echoview-frame-check-') as directory:
    os.environ['VIEWER_HOME'] = os.environ['IMAGE_DIR'] = directory
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PIL import Image, ImageDraw
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QImage, QPixmap, QMovie
    from PySide6.QtWidgets import QApplication
    from PySide6.QtMultimedia import QVideoFrame
    from echoview import viewer
    from echoview.preview_capture import capture_background
    from echoview.overlay_preview import FrameReceiver, request_frame
    from echoview.image_preloader import ImagePreloader

    app = QApplication([])
    display = {'mode': 'calibration'}
    cfg = {'displays': {'fixture': display}, 'gui': {'background_blur_radius': 0}}
    viewer.load_config = lambda: cfg
    window = viewer.DisplayWindow('fixture', display, app.primaryScreen())
    root = Path(directory)
    source = root / 'colour.png'
    image = Image.new('RGB', (800, 800), '#db2030')
    draw = ImageDraw.Draw(image)
    draw.rectangle((400, 0, 800, 800), fill='#2060d0')
    image.save(source)
    window.show_foreground_image(str(source))
    app.processEvents()
    before = capture_background(window)
    window._set_overlay({'clock_enabled': True, 'clock_font_size': 80, 'font_color': '#00ff00', 'clock_position': 'top-left'})
    window.setup_layout()
    app.processEvents()
    clock_state = (window.clock_label.isVisible(), window.clock_label.text(), window.clock_label.geometry())
    after = capture_background(window)
    assert before == after, 'The running clock must not be baked into the background'
    assert clock_state == (window.clock_label.isVisible(), window.clock_label.text(), window.clock_label.geometry())
    assert max(after[:2]) <= 640
    pixels = Image.frombytes('RGBA', after[:2], after[2])
    assert pixels.getpixel((pixels.width//4, pixels.height//2))[:3] == (219, 32, 48)
    assert pixels.getpixel((pixels.width*3//4, pixels.height//2))[:3] == (32, 96, 208)
    # Capturing the prepared image must not touch its source again.
    source.unlink()
    assert capture_background(window) == after

    # An actual QVideoSink frame is rendered rather than QVideoWidget's black
    # placeholder. This does not start a player or open a video file.
    window.foreground_label.hide()
    video = QImage(64, 64, QImage.Format_RGB32)
    video.fill('#123456')
    window.hls_video_widget.videoSink().setVideoFrame(QVideoFrame(video))
    window.hls_video_widget.show()
    window.setup_layout()
    app.processEvents()
    width, height, rgba = capture_background(window)
    pixel = Image.frombytes('RGBA', (width,height), rgba).getpixel((width//2,height//2))[:3]
    assert max(abs(a-b) for a,b in zip(pixel,(18,52,86))) <= 3, pixel
    window.hls_video_widget.hide()
    window.foreground_label.show()

    # External-player capture targets the assigned screen, without virtual
    # desktop offsets that would select the wrong output on X11.
    assigned = window.assigned_screen
    calls = []
    window.current_video_proc = SimpleNamespace(poll=lambda: None)
    window.assigned_screen = SimpleNamespace(grabWindow=lambda *args: calls.append(args) or QPixmap.fromImage(video))
    try:
        width, height, rgba = capture_background(window)
        assert calls == [(0,)]
        assert Image.frombytes('RGBA',(width,height),rgba).getpixel((0,0))[:3] == (18,52,86)
    finally:
        window.assigned_screen = assigned
        window.current_video_proc = None

    # End-to-end request/capture/background encoding while a GIF and heartbeat
    # keep running. Only the viewer thread is allowed to capture.
    gif = root/'moving.gif'
    frames = [Image.new('RGB',(128,128),c) for c in ('red','blue')]
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=80, loop=0)
    window.show_foreground_image(str(gif))
    movie = window.current_movie
    events, beats, results, failures, capture_times = [], [], [], [], []
    movie.frameChanged.connect(lambda _: events.append(1))
    encoder = ImagePreloader('test-preview-encoder')
    main_thread = threading.get_ident()
    def capture(name):
        assert name == 'fixture' and threading.get_ident() == main_thread
        start = time.monotonic()
        data = capture_background(window)
        capture_times.append(time.monotonic()-start)
        return data
    receiver = FrameReceiver(root/'preview', capture, encoder.submit)
    poll, heartbeat = QTimer(), QTimer()
    poll.timeout.connect(receiver.poll); poll.start(25)
    heartbeat.timeout.connect(lambda: beats.append(time.monotonic())); heartbeat.start(20)
    def client():
        try:
            for _ in range(6):
                result = request_frame(root/'preview', 'fixture')
                decoded = Image.open(BytesIO(result)); decoded.load()
                results.append(decoded.getpixel((decoded.width//2, decoded.height//2)))
                time.sleep(.1)
        except Exception as exc:
            failures.append(type(exc).__name__)
    worker = threading.Thread(target=client, daemon=True); worker.start()
    deadline = time.monotonic()+8
    while worker.is_alive() and time.monotonic()<deadline:
        app.processEvents(); time.sleep(.003)
    worker.join(timeout=.1)
    assert not worker.is_alive() and not failures, failures
    assert len(results)==6 and len(set(results))>=2 and len(events)>=4 and len(beats)>=10
    assert movie is window.current_movie and movie.state()==QMovie.MovieState.Running
    assert max(capture_times)<.3, capture_times
    assert clock_state[0] == window.clock_label.isVisible()
    encoder.close(); encoder.thread.join(timeout=1)
    window.close()
    print(f'Viewer previews: cached colours, clock excluded/unchanged, video sink, assigned-screen capture, animated JPEGs and active timers passed; max GUI capture {max(capture_times)*1000:.1f}ms.')
