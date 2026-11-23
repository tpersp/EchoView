from pathlib import Path
import pytest
from echoview import video_rendering


@pytest.mark.parametrize('model,enabled', [
    ('Raspberry Pi 4 Model B Rev 1.5\x00', True),
    ('Raspberry Pi 3 Model B Plus Rev 1.3\x00', True),
    ('Raspberry Pi 5 Model B Rev 1.0\x00', True),
    ('Other ARM board', False),
])
def test_scaling_policy_is_pi_only_and_detection_is_cached(monkeypatch, model, enabled):
    reads=[]
    def read(path):reads.append(str(path));return model
    video_rendering.scaling_flags.cache_clear()
    monkeypatch.setattr(Path, 'read_text', read)
    try:
        flags=video_rendering.scaling_flags()
        assert bool(flags)==enabled
        if enabled:assert flags==('--scale=bilinear','--cscale=bilinear','--dscale=bilinear')
        assert video_rendering.scaling_flags()==flags
        assert reads==['/proc/device-tree/model']
    finally:video_rendering.scaling_flags.cache_clear()


def test_unknown_hardware_keeps_player_defaults(monkeypatch):
    def unavailable(path):raise OSError('unavailable')
    monkeypatch.setattr(Path,'read_text',unavailable)
    video_rendering.scaling_flags.cache_clear()
    try:assert video_rendering.scaling_flags()==()
    finally:video_rendering.scaling_flags.cache_clear()
