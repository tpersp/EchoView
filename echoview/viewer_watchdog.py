"""Low-frequency event-loop heartbeat; never inspect frame locals or media."""
import os
import sys
import threading
import time


def main_stack(thread_id):
    frame = sys._current_frames().get(thread_id)
    frames = []
    try:
        while frame is not None and len(frames) < 8:
            code = frame.f_code
            frames.append(f'{os.path.basename(code.co_filename)}:{frame.f_lineno}:{code.co_name}')
            frame = frame.f_back
        return ' <- '.join(frames) or 'unavailable'
    finally:
        del frame


class ViewerWatchdog:
    def __init__(self, report, clock=time.monotonic, snapshot=main_stack,
                 threshold=0.75, cooldown=30):
        self.report, self.clock, self.snapshot = report, clock, snapshot
        self.threshold, self.cooldown = threshold, cooldown
        self.thread_id = threading.get_ident()
        self.lock = threading.Lock()
        self.last_beat = clock()
        self.stack = None
        self.pending = None
        self.last_report = float('-inf')
        self.suppressed = 0
        self.stop_event = threading.Event()
        self.thread = None

    def beat(self):
        # Qt only updates small in-memory state. Logging happens on the worker.
        now = self.clock()
        with self.lock:
            gap = now - self.last_beat
            if gap >= self.threshold:
                previous = self.pending
                if previous is None or gap > previous[0]:
                    self.pending = (gap, self.stack or 'not sampled (native work or GIL held)')
            self.last_beat, self.stack = now, None

    def check(self):
        now = self.clock()
        with self.lock:
            if now - self.last_beat >= self.threshold and self.stack is None:
                self.stack = self.snapshot(self.thread_id)
            pending, self.pending = self.pending, None
        if pending is None:
            return
        if now - self.last_report < self.cooldown:
            self.suppressed += 1
            return
        duration, stack = pending
        self.report(f'Viewer event loop delayed {duration:.2f}s between heartbeats '
                    f'(normal interval 0.25s; additional events since last report: '
                    f'{self.suppressed}). Python stack: {stack}')
        self.last_report, self.suppressed = now, 0

    def start(self):
        if self.thread is not None:
            return

        def worker():
            while not self.stop_event.wait(0.25):
                try:
                    self.check()
                except Exception:
                    # A diagnostic failure must never affect playback.
                    pass

        self.thread = threading.Thread(target=worker, name='viewer-watchdog', daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
