"""Bounded concurrent preloading + QMovie stress check; synthetic media only.

Run this in a subprocess with a 20-second external timeout: a GIL/Qt codec lock
deadlock also prevents Python timers and watchdog threads from running.
"""
from pathlib import Path
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice, QTimer
from PySide6.QtGui import QGuiApplication, QMovie
from echoview.image_data import read_image_data
from echoview.presentation import resource_settings

app = QGuiApplication([])
policy = resource_settings('standard', {})
with tempfile.TemporaryDirectory(prefix='echoview-codec-concurrency-') as directory:
    root = Path(directory)
    gif = root / 'animation.gif'
    frames = [Image.new('RGB', (128, 96), c) for c in ('red', 'green', 'blue')]
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=20, loop=0)
    png, jpeg = root / 'image.png', root / 'image.jpg'
    Image.new('RGBA', (256, 128), (20, 40, 60, 80)).save(png)
    Image.new('RGB', (192, 128), 'blue').save(jpeg)
    paths = [str(gif), str(png), str(jpeg)]
    encoded = read_image_data(str(gif), policy)['encoded']
    stop = threading.Event()
    counts, errors, workers = [0, 0], [], []

    def decode(index):
        try:
            while not stop.is_set():
                data = read_image_data(paths[counts[index] % len(paths)], policy)
                assert not data['image'].isNull()
                counts[index] += 1
                time.sleep(0.001)
        except Exception as exc:
            errors.append(type(exc).__name__)

    current, painted, beats = [None], [0], []

    def paint(_):
        painted[0] += 1

    def switch():
        if current[0]:
            current[0].stop()
            current[0].deleteLater()
        device = QBuffer()
        device.setData(encoded)
        device.open(QIODevice.ReadOnly)
        movie = QMovie(device)
        device.setParent(movie)
        movie.frameChanged.connect(paint)
        current[0] = movie
        movie.start()

    switch()
    for index in range(2):
        thread = threading.Thread(target=decode, args=(index,), daemon=True)
        thread.start()
        workers.append(thread)
    heartbeat, transitions = QTimer(), QTimer()
    heartbeat.timeout.connect(lambda: beats.append(time.monotonic()))
    heartbeat.start(20)
    transitions.timeout.connect(switch)
    transitions.start(50)
    QTimer.singleShot(5000, app.quit)
    app.exec()
    stop.set()
    for worker in workers:
        worker.join(timeout=2)
    assert not errors and all(not t.is_alive() for t in workers), errors
    assert min(counts) >= 40 and len(beats) >= 100 and painted[0] >= 20, (counts, len(beats), painted)
    gap = max(b - a for a, b in zip(beats, beats[1:]))
    assert gap < 0.75, gap
    current[0].stop()
    print(f'Concurrent image decode + QMovie: {sum(counts)} loads, {painted[0]} frames, maximum heartbeat gap {gap:.3f}s.')
