import threading

from echoview.image_preloader import ImagePreloader


def test_worker_reused_and_failures_do_not_stop_next_task():
    worker = ImagePreloader()
    done = threading.Event()
    threads = []
    try:
        def first():
            threads.append(threading.get_ident())
            raise OSError('synthetic read failure')

        def second():
            threads.append(threading.get_ident())
            done.set()

        assert worker.submit(first) and worker.submit(second)
        assert done.wait(2)
        assert threads == [worker.thread.ident, worker.thread.ident]
        assert worker.thread.daemon
    finally:
        worker.close()
        worker.thread.join(timeout=1)
    assert not worker.thread.is_alive()


def test_queue_is_bounded_and_close_does_not_wait_for_slow_io():
    worker = ImagePreloader()
    started, release = threading.Event(), threading.Event()
    calls = []
    try:
        def slow():
            started.set()
            release.wait(3)

        assert worker.submit(slow) and started.wait(2)
        assert worker.submit(lambda: calls.append(1))
        assert worker.submit(lambda: calls.append(2))
        assert not worker.submit(lambda: calls.append(3))
        worker.close()
        assert worker.thread.is_alive()  # Close returned without waiting on I/O.
        assert not worker.submit(lambda: calls.append(4))
    finally:
        release.set()
        worker.close()
        worker.thread.join(timeout=1)
    assert not calls and not worker.thread.is_alive()


def test_latest_requests_replace_queued_work_without_waiting_for_running_io():
    worker = ImagePreloader()
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    calls = []
    try:
        assert worker.submit(lambda: (started.set(), release.wait(3)))
        assert started.wait(2)
        for i in range(10):
            assert worker.submit(lambda n=i: (calls.append(n), finished.set()), replace_pending=True)
        assert worker.tasks.qsize() == 1
        release.set()
        assert finished.wait(2)
        assert calls == [9]
    finally:
        release.set()
        worker.close()
        worker.thread.join(timeout=1)
