from dataclasses import replace
from pathlib import Path
import json

from PIL import Image
from flask import Flask
from echoview.spotify_client import Playback
from echoview.spotify_state import StatePublisher, read_state
from echoview.web import routes


def test_snapshot_interpolation_privacy_and_staleness(tmp_path):
    cfg = {'client_id': 'id', 'client_secret': 'private-secret'}
    publisher = StatePublisher(tmp_path, clock=lambda: 100, monotonic=lambda: 12)
    result = Playback('playing', song='<script>Title</script>', progress_ms=1000,
                      duration_ms=10000, fetched_time=10, device_name='Kitchen', art_colors=('#ff0000','#0000ff'))
    publisher(result, cfg)
    state = read_state(tmp_path, cfg, True, now=103)
    assert state['progress_ms'] == 6000
    assert state['device_name'] == 'Kitchen'
    assert state['art_colors']==['#ff0000','#0000ff']
    assert 'account' not in state and 'sampled_at' not in state
    assert 'private-secret' not in (tmp_path/'state.json').read_text()
    assert (tmp_path/'state.json').stat().st_mode & 0o777 == 0o600
    assert read_state(tmp_path, cfg, True, now=150) == {'status': 'stale'}
    assert read_state(tmp_path, {'client_id': 'other'}, True, now=101) == {'status': 'waiting'}
    assert read_state(tmp_path, cfg, False) == {'status': 'inactive'}
    publisher(replace(result, status='paused'), cfg)
    assert read_state(tmp_path, cfg, True, now=103)['progress_ms'] == 1000


def test_artwork_is_resized_cached_and_bounded(tmp_path):
    image = tmp_path/'source.png'
    Image.new('RGB', (800, 800), 'red').save(image)
    directory = tmp_path/'state'
    publisher = StatePublisher(directory, clock=lambda: 100, monotonic=lambda: 10)
    for i in range(4):
        publisher(Playback('playing', art_url=f'url-{i}', art_path=str(image), fetched_time=10), {})
    images = list(directory.glob('art-*.jpg'))
    assert len(images) == 2
    for path in images:
        with Image.open(path) as thumbnail:
            assert thumbnail.size == (320,320)
    previous = json.loads((directory/'state.json').read_text())['artwork']
    publisher(Playback('paused', art_url='url-3', fetched_time=10), {})
    assert json.loads((directory/'state.json').read_text())['artwork'] == previous
    assert image.exists()  # Source is never modified or deleted.


def test_missing_or_broken_snapshot_is_waiting(tmp_path):
    assert read_state(tmp_path, {}, True) == {'status': 'waiting'}
    (tmp_path/'state.json').write_text('broken')
    assert read_state(tmp_path, {}, True) == {'status': 'waiting'}


def test_web_snapshot_and_artwork_never_call_spotify(tmp_path, monkeypatch):
    cfg = {'displays': {'HDMI-1': {'mode': 'spotify'}}, 'spotify': {'client_id': 'id'}}
    publisher = StatePublisher(tmp_path)
    image = tmp_path/'source.png'
    Image.new('RGB', (32,32), 'blue').save(image)
    import time
    publisher(Playback('playing', song='Song', fetched_time=time.monotonic(), art_url='url', art_path=str(image)), cfg['spotify'])
    monkeypatch.setattr(routes, 'load_config', lambda: cfg)
    monkeypatch.setattr(routes, 'state_directory', lambda _: tmp_path)
    monkeypatch.setattr(routes, 'oauth_client', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('API call')))
    app = Flask(__name__)
    app.register_blueprint(routes.main_bp)
    client = app.test_client()
    response = client.get('/spotify/now-playing')
    assert response.json['song'] == 'Song'
    assert response.headers['Cache-Control'] == 'no-store'
    assert client.get(response.json['artwork']).status_code == 200
    assert client.get('/spotify/artwork/not-a-key.jpg').status_code == 404
    cfg['displays']['HDMI-1']['mode'] = 'random_image'
    assert client.get('/spotify/now-playing').json == {'status': 'inactive'}
