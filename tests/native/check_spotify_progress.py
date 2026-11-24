"""Native Qt rendering/animation check; no Spotify API or source media access."""
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from echoview.progress_bar import SmoothProgressBar
from echoview.spotify_progress import ProgressTimeline

app = QApplication([])
bar = SmoothProgressBar()
bar.setRange(0, 10000)
bar.resize(600, 10)
bar.show()
for theme in bar.THEMES:
    bar.setTheme(theme)
    bar.setFraction(0.5)
    app.processEvents()
    first = bar.grab().toImage()
    bar.setFraction(0.5002)  # 0.12 pixel movement must be visible.
    app.processEvents()
    second = bar.grab().toImage()
    assert first != second, theme
    assert bar.value() == 5002
bar.setTheme('spotify')
timeline = ProgressTimeline()
start = time.monotonic()
timeline.sample('track', 18000, 180000, start, start)
values = []
timer = QTimer()
def frame():
    bar.setFraction(timeline.position(time.monotonic()) / 180000)
    values.append(bar.value())
timer.timeout.connect(frame)
timer.start(50)
cpu_start = time.process_time()
QTimer.singleShot(3000, app.quit)
app.exec()
elapsed = time.monotonic() - start
assert len(values) >= 40, len(values)
assert values[-1] > values[0]
assert values == sorted(values)
print('Native Qt: all themes render fractional movement; frames:', len(values),
      'CPU % of one core:', round((time.process_time()-cpu_start)/elapsed*100, 2))
