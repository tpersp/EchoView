import fcntl
from io import BytesIO
import json
import os
import threading
import time

from PIL import Image
import pytest

from echoview.image_preloader import ImagePreloader
from echoview.live_settings import atomic_json
from echoview.overlay_preview import FrameReceiver, PreviewUnavailable, request_frame


def test_frame_roundtrip_is_private_bounded_and_encoded_off_capture_thread(tmp_path):
    captured, encoders, result = [], [], []
    worker = ImagePreloader()
    def submit(job):
        return worker.submit(lambda: (encoders.append(threading.get_ident()), job()))
    receiver = FrameReceiver(tmp_path, lambda display: (captured.append((display, threading.get_ident())) or
                                                      (2, 2, bytes([230, 20, 40, 255])*4)), submit)
    client = threading.Thread(target=lambda: result.append(request_frame(tmp_path, 'HDMI-1', timeout=1)))
    try:
        client.start()
        deadline = time.monotonic()+2
        while client.is_alive() and time.monotonic()<deadline:
            receiver.poll()
            time.sleep(.005)
        client.join(timeout=.1)
        assert not client.is_alive() and len(result) == 1
        assert captured == [('HDMI-1', threading.get_ident())]
        assert encoders == [worker.thread.ident]
        assert Image.open(BytesIO(result[0])).size == (2, 2)
        receiver.poll()
        assert len(captured) == 1
        assert set(p.name for p in tmp_path.iterdir()) == {'lock', 'request.json', 'response.json'}
        assert all(p.stat().st_mode & 0o777 == 0o600 for p in tmp_path.iterdir())
    finally:
        worker.close()
        worker.thread.join(timeout=1)


def test_unavailable_or_busy_viewer_has_bounded_wait(tmp_path):
    with pytest.raises(PreviewUnavailable, match='Viewer unavailable'):
        request_frame(tmp_path, 'HDMI-1', timeout=.02)
    fd = os.open(tmp_path/'lock', os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        with pytest.raises(PreviewUnavailable, match='busy'):
            request_frame(tmp_path, 'HDMI-1', timeout=.02)
    finally:
        os.close(fd)


@pytest.mark.parametrize('payload', [
    {'revision':'bad', 'display':'HDMI-1', 'expires':time.time()+3},
    {'revision':'a'*32, 'display':'HDMI-1', 'expires':0},
    {'revision':'a'*32, 'display':[], 'expires':time.time()+3},
])
def test_malformed_expired_requests_never_capture(tmp_path, payload):
    atomic_json(tmp_path, 'request.json', payload)
    receiver = FrameReceiver(tmp_path, lambda _: pytest.fail('Invalid request captured'), lambda _: False)
    receiver.poll()
    assert not (tmp_path/'response.json').exists()


def test_capture_failures_and_storage_failures_do_not_affect_viewer(tmp_path, monkeypatch):
    import echoview.overlay_preview as module
    atomic_json(tmp_path, 'request.json', dict(revision='a'*32, display='missing', expires=time.time()+3))
    receiver = FrameReceiver(tmp_path, lambda _: (_ for _ in ()).throw(ValueError()), lambda _: False)
    receiver.poll()
    assert json.loads((tmp_path/'response.json').read_text())['error'] is True
    receiver.stamp = None
    monkeypatch.setattr(module, 'atomic_json', lambda *a: (_ for _ in ()).throw(OSError()))
    receiver.poll()


def test_oversized_captures_are_rejected_before_encoding(tmp_path):
    atomic_json(tmp_path, 'request.json', dict(revision='a'*32, display='HDMI-1', expires=time.time()+3))
    receiver = FrameReceiver(tmp_path, lambda _: (1000, 1000, b''), lambda _: pytest.fail('Oversized encode'))
    receiver.poll()
    assert json.loads((tmp_path/'response.json').read_text())['error'] is True


def test_gui_capture_rate_is_bounded_across_clients(tmp_path, monkeypatch):
    import echoview.overlay_preview as module
    now, captures = [100], []
    monkeypatch.setattr(module.time, 'monotonic', lambda: now[0])
    receiver = FrameReceiver(tmp_path, lambda name: captures.append(name) or (1, 1, b'\0'*4), lambda _: True)
    atomic_json(tmp_path, 'request.json', dict(revision='a'*32, display='one', expires=time.time()+3))
    receiver.poll()
    atomic_json(tmp_path, 'request.json', dict(revision='b'*32, display='two', expires=time.time()+3))
    now[0] += .1
    receiver.poll()
    assert captures == ['one']
    now[0] += .5
    receiver.poll()
    assert captures == ['one', 'two']
