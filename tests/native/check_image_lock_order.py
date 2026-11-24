"""Exercise codec discovery while a Python-backed device holds its Qt lock.

Run in a subprocess with an external timeout; the old decoder can hold the GIL
while waiting for that lock, preventing even Python timeouts from firing.
"""
from pathlib import Path
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PIL import Image
from PySide6.QtCore import QBuffer, QCoreApplication, QIODevice
from PySide6.QtGui import QImageReader
from echoview.image_data import read_image_data
from echoview.presentation import resource_settings

app = QCoreApplication([])
entered, finished = threading.Event(), threading.Event()
errors = []


class CoordinatedBuffer(QBuffer):
    def readLineData(self, maximum):
        if not entered.is_set():
            entered.set()
            assert finished.wait(3), 'Background decoder blocked by Qt codec discovery'
        return super().readLineData(maximum)


with tempfile.TemporaryDirectory(prefix='echoview-codec-lock-') as directory:
    path = Path(directory) / 'image.png'
    Image.new('RGB', (32, 24), 'red').save(path)

    def worker():
        try:
            assert entered.wait(3), 'Qt did not enter the coordinated device callback'
            assert not read_image_data(str(path), resource_settings('standard', {}))['image'].isNull()
        except Exception as exc:
            errors.append(type(exc).__name__)
        finally:
            finished.set()

    background = threading.Thread(target=worker, daemon=True)
    background.start()
    device = CoordinatedBuffer()
    device.setData(b'#define icon_width 8\n#define icon_height 1\nstatic unsigned char icon_bits[] = { 0xff };\n')
    device.open(QIODevice.ReadOnly)
    reader = QImageReader(device)
    image = reader.read()
    background.join(timeout=2)
    assert entered.is_set() and finished.is_set() and not errors, errors
    assert not image.isNull()
print('Codec lock ordering: background decoding completes while Qt codec discovery owns a Python-backed device.')
