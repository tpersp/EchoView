from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
import threading
from types import SimpleNamespace

from PIL import Image
import pytest

from echoview import spotify_client as spotify


def settings():
    return {"spotify": {"client_id": "id", "client_secret": "secret", "redirect_uri": "https://pi/callback"}}


def playing(url=None):
    return {"is_playing": True, "progress_ms": 1500, "item": {
        "name": "Song", "artists": [{"name": "Artist"}], "duration_ms": 10000,
        "album": {"name": "Album", "images": [{"url": url}] if url else []},
    }}


def test_overlapping_displays_share_one_request_and_result(tmp_path):
    entered, release = threading.Event(), threading.Event()
    calls = []
    class Client:
        def current_playback(self, **kwargs):
            assert kwargs == {"additional_types": "track,episode"}
            calls.append(1)
            entered.set()
            assert release.wait(2)
            return playing()
    poller = spotify.SpotifyPoller(settings, tmp_path / "token", client_factory=lambda cfg: Client())
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(poller.fetch)
        assert entered.wait(1)
        others = [pool.submit(poller.fetch) for _ in range(2)]
        release.set()
        results = [first.result()] + [job.result() for job in others]
    assert len(calls) == 1
    assert results[0] is results[1] is results[2]
    with pytest.raises(AttributeError):
        results[0].song = "changed"


def test_poll_interval_and_config_change(tmp_path):
    now = [100]
    cfg = settings()
    calls = []
    client = SimpleNamespace(current_playback=lambda **kwargs: calls.append(1) or playing())
    poller = spotify.SpotifyPoller(lambda: cfg, tmp_path / "token", clock=lambda: now[0], client_factory=lambda cfg: client)
    poller.fetch()
    now[0] += 4
    poller.fetch()
    assert len(calls) == 1
    now[0] += 1
    poller.fetch()
    assert len(calls) == 2
    cfg["spotify"]["client_id"] = "changed"
    poller.fetch()
    assert len(calls) == 3


@pytest.mark.parametrize("payload, status", [(None, "unavailable"), ({}, "unavailable"),
    ({"is_playing": True, "currently_playing_type": "ad", "item": {}}, "unavailable"),
    ({"is_playing": False, "item": {"album": None, "artists": None}}, "paused")])
def test_unavailable_paused_and_ads(payload, status):
    assert spotify.normalize_playback(payload, 1).status == status


def test_episode_and_null_fields():
    result = spotify.normalize_playback({"is_playing": True, "currently_playing_type": "episode",
        "progress_ms": None, "item": {"name": "Episode", "duration_ms": None,
        "images": [{"url": "https://art"}], "show": {"name": "Show", "publisher": "Host"}}}, 10)
    assert (result.song, result.artist, result.album) == ("Episode", "Host", "Show")
    assert result.progress_ms == result.duration_ms == 0
    assert result.art_url == "https://art"


class ProviderError(Exception):
    def __init__(self, status=None, headers=None, msg="", reason=None):
        self.http_status, self.headers, self.msg, self.reason = status, headers, msg, reason


@pytest.mark.parametrize("error,status,delay", [
    (ProviderError(401), "authorization_required", 60),
    (ProviderError(403), "access_denied", 60),
    (ProviderError(429, {"Retry-After": "120"}), "rate_limited", 120),
    (ProviderError(429, {"retry-after": "900"}, msg='{"reason":"QUOTA_EXCEEDED"}'), "quota_exceeded", 900),
    (ProviderError(429, {"Retry-After": "invalid"}), "rate_limited", 30),
    (ProviderError(429, {"Retry-After": "inf"}), "rate_limited", 30),
    (OSError("network"), "offline", 10),
])
def test_error_backoff_does_not_retry_early(tmp_path, error, status, delay):
    now = [100]
    calls = []
    def fail(cfg):
        calls.append(1)
        raise error
    poller = spotify.SpotifyPoller(settings, tmp_path / "token", clock=lambda: now[0], client_factory=fail)
    assert poller.fetch().status == status
    now[0] += delay - 1
    assert poller.fetch().status == status
    assert len(calls) == 1
    now[0] += 1
    poller.fetch()
    assert len(calls) == 2


def test_no_token_and_missing_credentials(tmp_path):
    poller = spotify.SpotifyPoller(settings, tmp_path / "token", client_factory=lambda cfg: None)
    assert poller.fetch().status == "authorization_required"
    poller = spotify.SpotifyPoller(lambda: {}, tmp_path / "token", client_factory=lambda cfg: pytest.fail("no credentials"))
    assert poller.fetch().status == "authorization_required"


def png():
    output = BytesIO()
    Image.new("RGB", (2, 2), "red").save(output, format="PNG")
    return output.getvalue()


class Response:
    def __init__(self, data):
        self.data = data
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def raise_for_status(self):
        pass
    def iter_content(self, size):
        yield self.data


def test_artwork_is_reused_bounded_and_cleaned_up(tmp_path, monkeypatch):
    from echoview import spotify_background
    palette_calls=[]
    original=spotify_background.extract_palette
    monkeypatch.setattr(spotify_background,'extract_palette',lambda image: palette_calls.append(1) or original(image))
    calls = []
    def get(url, **kwargs):
        assert kwargs["timeout"] == (3, 5)
        calls.append(url)
        return Response(png())
    poller = spotify.SpotifyPoller(settings, tmp_path / "token", artwork_get=get)
    first = poller._artwork("https://art/0")
    assert Path(first).exists()
    assert poller._artwork("https://art/0") == first
    assert len(calls) == 1
    assert len(palette_calls)==1 and len(poller.art_palettes['https://art/0'])==2
    for i in range(1, 9):
        poller._artwork(f"https://art/{i}")
    assert len(poller.art_cache) == 8
    assert len(poller.art_palettes)==8 and 'https://art/0' not in poller.art_palettes
    assert not Path(first).exists()
    directory = Path(poller.art_dir.name)
    poller.close()
    assert not poller.art_palettes
    assert not directory.exists()


def test_palette_failure_keeps_valid_artwork(tmp_path,monkeypatch):
    from echoview import spotify_background
    monkeypatch.setattr(spotify_background,'extract_palette',lambda _: (_ for _ in ()).throw(RuntimeError()))
    poller=spotify.SpotifyPoller(settings,tmp_path/'token',artwork_get=lambda *a,**kw: Response(png()))
    try:
        path=poller._artwork('https://art/valid')
        assert path and Path(path).exists()
        assert poller.art_palettes['https://art/valid']==()
    finally:
        poller.close()


def test_paused_track_reuses_palette_without_another_artwork_download(tmp_path):
    now=[100]
    current=playing('https://art/cover')
    calls=[]
    def download(url,**kwargs):
        calls.append(url)
        return Response(png())
    client=SimpleNamespace(current_playback=lambda **kwargs: current)
    poller=spotify.SpotifyPoller(settings,tmp_path/'token',clock=lambda:now[0],
                                client_factory=lambda cfg:client,artwork_get=download)
    try:
        first=poller.fetch()
        assert first.art_colors
        current['is_playing']=False
        now[0]+=6
        paused=poller.fetch()
        assert paused.status=='paused' and paused.art_colors==first.art_colors
        assert len(calls)==1
    finally:
        poller.close()


@pytest.mark.parametrize("data", [b"not an image", b"x" * (spotify.MAX_ART_BYTES + 1)])
def test_invalid_or_oversized_art_keeps_metadata_and_throttles_retries(tmp_path, data):
    now, calls = [100], []
    def get(url, **kwargs):
        calls.append(url)
        return Response(data)
    poller = spotify.SpotifyPoller(settings, tmp_path / "token", clock=lambda: now[0], artwork_get=get,
        client_factory=lambda cfg: SimpleNamespace(current_playback=lambda **kwargs: playing("https://art")))
    result = poller.fetch()
    assert result.status == "playing" and result.song == "Song" and not result.art_path
    now[0] += 5
    poller.fetch()
    assert len(calls) == 1
    assert not list(Path(poller.art_dir.name).iterdir())
    poller.close()


def test_token_validation_is_serialized_and_uses_refreshed_token(tmp_path, monkeypatch):
    import sys
    import types
    calls = []
    class OAuth:
        def __init__(self, **kwargs):
            assert kwargs["open_browser"] is False
            assert kwargs["requests_timeout"] == 5
        def get_cached_token(self):
            calls.append("validate-refresh")
            return {"access_token": "refreshed"}
    class Client:
        def __init__(self, **kwargs):
            assert kwargs["auth"] == "refreshed"
            assert kwargs["retries"] == kwargs["status_retries"] == 0
        def current_playback(self, **kwargs):
            calls.append("playback")
            return None
    monkeypatch.setitem(sys.modules, "spotipy", types.SimpleNamespace(Spotify=Client))
    monkeypatch.setitem(sys.modules, "spotipy.oauth2", types.SimpleNamespace(SpotifyOAuth=OAuth))
    poller = spotify.SpotifyPoller(settings, tmp_path / "token")
    poller.fetch()
    poller.fetch()
    assert calls == ["validate-refresh", "playback"]
    poller.close()


def test_pkce_polling_without_client_secret(tmp_path):
    cfg = settings()
    cfg['spotify'].update(auth_method='pkce', client_secret='')
    calls = []
    class Client:
        def current_playback(self, **kwargs):
            calls.append('playback')
            return None
    poller = spotify.SpotifyPoller(lambda: cfg, tmp_path / 'token', client_factory=lambda _: Client())
    assert poller.fetch().status == 'unavailable'
    assert calls == ['playback']
    poller.close()


def test_slow_requests_and_artwork_do_not_add_an_extra_poll_period(tmp_path):
    now = [100.0]
    calls = []
    def playback(**kwargs):
        calls.append(now[0])
        now[0] += 0.25
        return playing('https://art')
    poller = spotify.SpotifyPoller(settings, tmp_path / 'token', clock=lambda: now[0],
                                  client_factory=lambda _: SimpleNamespace(current_playback=playback))
    def artwork(url):
        now[0] += 0.75
        return '/cached/art.jpg'
    poller._artwork = artwork
    result = poller.fetch()
    assert now[0] == 101
    assert result.next_poll_at == 105
    now[0] = 104.99
    assert poller.fetch() is result
    now[0] = 105
    poller.fetch()
    assert calls == [100, 105]


def test_expected_track_end_checks_earlier_then_returns_to_normal_cadence(tmp_path):
    now = [100.0]
    payload = playing()
    payload['progress_ms'] = 9000
    poller = spotify.SpotifyPoller(settings, tmp_path / 'token', clock=lambda: now[0],
                                  client_factory=lambda _: SimpleNamespace(current_playback=lambda **kw: payload))
    assert poller.fetch().next_poll_at == 102
    # Spotify may still report the old track at its end. Do not hammer it.
    now[0] = 102
    payload['progress_ms'] = 10000
    assert poller.fetch().next_poll_at == 107


def test_stale_near_end_position_does_not_keep_polling_faster(tmp_path):
    now = [100.0]
    payload = playing()
    payload['progress_ms'] = 9000
    poller = spotify.SpotifyPoller(settings, tmp_path / 'token', clock=lambda: now[0],
                                  client_factory=lambda _: SimpleNamespace(current_playback=lambda **kw: payload))
    assert poller.fetch().next_poll_at == 102
    now[0] = 102
    assert poller.fetch().next_poll_at == 107
    now[0] = 107
    payload['progress_ms'] = 1000  # A repeat or seek rearms the end check.
    assert poller.fetch().next_poll_at == 112
    now[0] = 112
    payload['progress_ms'] = 9000
    assert poller.fetch().next_poll_at == 114


def test_publisher_uses_existing_poll_and_failure_does_not_break_playback(tmp_path):
    now = [100.0]
    publications, calls = [], []
    def publish(result, cfg):
        publications.append(result.status)
        raise OSError('read-only snapshot directory')
    def playback(**kwargs):
        calls.append(1)
        payload = playing()
        payload.update(device={'name': 'Kitchen', 'type': 'speaker'}, shuffle_state=True, repeat_state='context')
        return payload
    poller = spotify.SpotifyPoller(settings, tmp_path/'token', clock=lambda: now[0],
                                  client_factory=lambda _: SimpleNamespace(current_playback=playback), publisher=publish)
    result = poller.fetch()
    assert result.status == 'playing' and result.device_name == 'Kitchen'
    assert result.shuffle is True and result.repeat == 'context'
    assert poller.fetch() is result
    assert len(calls) == len(publications) == 1
