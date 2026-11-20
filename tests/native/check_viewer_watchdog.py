"""Real Qt heartbeat check using a synthetic block, never live playback."""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PySide6.QtCore import QCoreApplication, QTimer
from echoview.viewer_watchdog import ViewerWatchdog

app = QCoreApplication([])
reports = []
main_thread = threading.get_ident()
monitor = ViewerWatchdog(lambda text: reports.append((threading.get_ident(), text)))
timer = QTimer()
timer.timeout.connect(monitor.beat)
timer.start(250)
app.aboutToQuit.connect(monitor.stop)
monitor.start()
QTimer.singleShot(500, lambda: time.sleep(1.1))
QTimer.singleShot(2400, app.quit)
app.exec()
monitor.thread.join(timeout=1)
assert len(reports) == 1, reports
assert reports[0][0] != main_thread
assert 'Viewer event loop delayed' in reports[0][1]
assert not monitor.thread.is_alive()
print('Qt heartbeat: synthetic stall detected, reporting stays off GUI thread, clean shutdown.')
