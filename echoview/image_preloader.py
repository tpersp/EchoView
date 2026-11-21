"""One bounded, reusable daemon worker per display; no Qt event-loop waits."""
import queue
import threading


class ImagePreloader:
    def __init__(self):
        self.tasks = queue.Queue(maxsize=2)
        self.closed = threading.Event()
        self.gate = threading.Lock()
        self.thread = threading.Thread(target=self._run, name='image-preloader', daemon=True)
        self.thread.start()

    def submit(self, task):
        with self.gate:
            if self.closed.is_set():
                return False
            try:
                self.tasks.put_nowait(task)
                return True
            except queue.Full:
                return False

    def _run(self):
        while True:
            task = self.tasks.get()
            try:
                if task is None:
                    return
                if not self.closed.is_set():
                    task()
            except Exception:
                pass  # Prefetch failure leaves the normal playback path available.
            finally:
                self.tasks.task_done()
                del task

    def close(self):
        # Never join a worker that may be waiting on a disconnected NAS.
        with self.gate:
            if self.closed.is_set():
                return
            self.closed.set()
            while True:
                try:
                    self.tasks.get_nowait()
                    self.tasks.task_done()
                except queue.Empty:
                    break
            self.tasks.put_nowait(None)
