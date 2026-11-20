import threading

from echoview.viewer_watchdog import ViewerWatchdog, main_stack


def fixture():
    now, reports = [0.0], []
    monitor = ViewerWatchdog(reports.append, clock=lambda: now[0],
                             snapshot=lambda _: 'viewer.py:10:example')
    return now, reports, monitor


def test_normal_heartbeat_does_not_log_or_sample():
    now, reports, monitor = fixture()
    monitor.snapshot = lambda _: (_ for _ in ()).throw(AssertionError('unnecessary sample'))
    for _ in range(20):
        now[0] += 0.25
        monitor.beat()
        monitor.check()
    assert reports == []


def test_stall_is_sampled_once_and_reported_after_recovery():
    now, reports, monitor = fixture()
    calls = []
    monitor.snapshot = lambda tid: calls.append(tid) or 'viewer.py:10:example'
    now[0] = 0.8
    monitor.check()
    now[0] = 1.0
    monitor.check()
    assert reports == [] and calls == [threading.get_ident()]
    now[0] = 1.5
    monitor.beat()
    assert reports == []  # Qt callback never logs.
    monitor.check()
    assert len(reports) == 1
    assert '1.50s' in reports[0] and 'viewer.py:10:example' in reports[0]
    monitor.check()
    assert len(reports) == 1


def test_gil_held_gap_is_detected_without_a_stack_sample():
    now, reports, monitor = fixture()
    now[0] = 2
    monitor.beat()
    monitor.check()
    assert '2.00s' in reports[0] and 'not sampled' in reports[0]


def test_report_limit_and_bounded_pending_state():
    now, reports, monitor = fixture()
    for _ in range(5):
        now[0] += 1
        monitor.beat()
        monitor.check()
    assert len(reports) == 1 and monitor.suppressed == 4
    now[0] = 32
    monitor.beat()
    monitor.check()
    assert len(reports) == 2 and 'additional events since last report: 4' in reports[1]
    assert monitor.pending is None and monitor.suppressed == 0


def test_stack_does_not_include_locals_source_or_full_paths():
    secret_value = 'private-token-do-not-log'
    snapshot = main_stack(threading.get_ident())
    assert secret_value not in snapshot
    assert 'test_stack_does_not_include_locals_source_or_full_paths' in snapshot
    assert __file__ not in snapshot
    assert len(snapshot.split(' <- ')) <= 8


def test_worker_can_stop_and_start_is_idempotent():
    _, _, monitor = fixture()
    monitor.start()
    thread = monitor.thread
    monitor.start()
    assert monitor.thread is thread and thread.daemon
    monitor.stop()
    thread.join(timeout=1)
    assert not thread.is_alive()
