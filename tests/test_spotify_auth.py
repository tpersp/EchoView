import json
import time
from urllib.parse import parse_qs, urlsplit

import pytest
from flask import Flask

from echoview.web import routes
from echoview.web import spotify_auth as auth


def config():
    return dict(client_id="id", client_secret="secret", redirect_uri="http://127.0.0.1:8080/callback", scope=auth.DEFAULT_SCOPE)


@pytest.mark.parametrize("uri", ["http://localhost:8080/callback", "http://192.168.1.2:8080/callback", "https://x/callback#fragment", "https://user:pass@x/callback", "https://x/other", "https://x:bad/callback", "https://x/callback?q=1"])
def test_redirect_rejected(uri):
    with pytest.raises(ValueError):
        auth.validate_config(dict(config(), redirect_uri=uri))


@pytest.mark.parametrize("uri", ["http://127.0.0.1:8080/callback", "http://[::1]:8080/callback", "https://controller.example/callback"])
def test_redirect_accepted(uri):
    auth.validate_config(dict(config(), redirect_uri=uri))


def test_required_scopes():
    with pytest.raises(ValueError):
        auth.validate_config(dict(config(), scope="user-read-currently-playing"))


def test_state_survives_restart_and_cannot_replay(tmp_path, monkeypatch):
    path = tmp_path / "states.sqlite3"
    first = auth.StateStore(path)
    state = first.issue("browser", config())
    second = auth.StateStore(path)
    assert first.secret() == second.secret()
    assert path.stat().st_mode & 0o777 == 0o600
    assert not second.consume(state, "other browser", config())
    assert not second.consume(state, "browser", dict(config(), client_secret="changed"))
    assert second.consume(state, "browser", config())
    assert not first.consume(state, "browser", config())
    now = time.time()
    state = first.issue("browser", config())
    monkeypatch.setattr(auth.time, "time", lambda: now + auth.STATE_TTL + 1)
    assert not first.consume(state, "browser", config())



def test_cache_health(tmp_path):
    path = tmp_path / "token"
    assert "authorize" in auth.cached_status(config(), path)
    path.write_text("broken json")
    assert "unreadable" in auth.cached_status(config(), path)
    token = dict(access_token="private", scope=auth.DEFAULT_SCOPE, expires_at=time.time() + 3600)
    path.write_text(json.dumps(token))
    assert auth.cached_status(config(), path) == "Cached token valid; connection not checked."
    token["scope"] = ""
    path.write_text(json.dumps(token))
    assert "permissions" in auth.cached_status(config(), path)
    token.update(scope=auth.DEFAULT_SCOPE, expires_at=0, refresh_token="private")
    path.write_text(json.dumps(token))
    assert "refresh available" in auth.cached_status(config(), path)


@pytest.fixture
def web(tmp_path, monkeypatch):
    cfg = {"spotify": config()}
    cache = tmp_path / "token"
    monkeypatch.setattr(routes, "SPOTIFY_CACHE_PATH", str(cache))
    monkeypatch.setattr(routes, "load_config", lambda: cfg)
    monkeypatch.setattr(routes, "save_config", lambda updated: None)
    calls = []

    class OAuth:
        def get_authorize_url(self, state):
            return "https://accounts.spotify.com/authorize?state=" + state

        def get_access_token(self, code, check_cache):
            assert check_cache is False
            calls.append(code)
            return {"access_token": "token", "scope": auth.DEFAULT_SCOPE}

    monkeypatch.setattr(routes, "oauth_client", lambda cfg, path: OAuth())
    app = Flask("echoview.web.app", template_folder="templates", static_folder="static")
    store = auth.StateStore(tmp_path / "states")
    app.secret_key = store.secret()
    app.extensions["spotify_states"] = store
    app.register_blueprint(routes.main_bp)
    return app.test_client(), cfg, cache, calls


def start(client):
    response = client.get("/spotify_auth")
    assert response.status_code == 302
    return parse_qs(urlsplit(response.location).query)["state"][0]


def test_callback_success_and_replay(web):
    client, cfg, cache, calls = web
    state = start(client)
    response = client.get("/callback", query_string={"state": state, "code": "code"})
    assert response.status_code == 302
    assert response.location == "/configure_spotify"
    assert client.get("/callback", query_string={"state": state, "code": "code"}).status_code == 400
    assert calls == ["code"]


@pytest.mark.parametrize("args", [{"code": "code"}, {"state": "wrong", "code": "code"}, {"error": "access_denied"}, {}])
def test_callback_failures_never_exchange(web, args):
    client, cfg, cache, calls = web
    state = start(client)
    query = {"state": state, **args} if "code" not in args else args
    assert client.get("/callback", query_string=query).status_code == 400
    assert calls == []


def test_config_change_invalidates_cache_and_pending_callback(web):
    client, cfg, cache, calls = web
    state = start(client)
    cache.write_text("old token")
    response = client.post("/configure_spotify", data=dict(config(), client_id="new"))
    assert response.status_code == 302
    assert not cache.exists()
    assert client.get("/callback", query_string={"state": state, "code": "code"}).status_code == 400
    assert calls == []


def test_invalid_config_preserves_cache(web):
    client, cfg, cache, calls = web
    cache.write_text("old token")
    assert client.post("/configure_spotify", data=dict(config(), redirect_uri="http://pi/callback")).status_code == 400
    assert cache.read_text() == "old token"


def test_exchange_error_does_not_leak_provider_details(web, monkeypatch):
    client, cfg, cache, calls = web
    state = start(client)
    def fail(*args):
        raise RuntimeError("private code and credentials")
    monkeypatch.setattr(routes, "oauth_client", fail)
    response = client.get("/callback", query_string={"state": state, "code": "secret-code"})
    assert response.status_code == 502
    assert b"private code" not in response.data
    assert b"secret-code" not in response.data


def test_page_reports_cache_health(web):
    client, cfg, cache, calls = web
    response = client.get("/configure_spotify")
    assert response.status_code == 200
    assert b"Credentials saved" in response.data
    assert b"Spotify authorized." not in response.data


@pytest.mark.parametrize("status, expected", [(401, 401), (403, 403), (429, 429), (None, 503)])
def test_connection_errors(web, monkeypatch, status, expected):
    client, cfg, cache, calls = web
    class ProviderError(Exception):
        http_status = status
    class OAuth:
        def get_cached_token(self):
            raise ProviderError("private-token")
    monkeypatch.setattr(routes, "oauth_client", lambda *args: OAuth())
    response = client.post("/spotify_check")
    assert response.status_code == expected
    assert b"private-token" not in response.data


def test_connection_refresh_and_no_playback_succeed(web, monkeypatch):
    import sys
    import types
    client, cfg, cache, calls = web
    class OAuth:
        def get_cached_token(self):
            calls.append("validate-and-refresh")
            return {"access_token": "refreshed"}
    class Spotify:
        def __init__(self, **kwargs):
            assert kwargs["auth"] == "refreshed"
            assert kwargs["retries"] == 0
        def current_playback(self):
            calls.append("api")
            return None
    monkeypatch.setattr(routes, "oauth_client", lambda *args: OAuth())
    monkeypatch.setitem(sys.modules, "spotipy", types.SimpleNamespace(Spotify=Spotify))
    assert client.post("/spotify_check").status_code == 200
    assert calls == ["validate-and-refresh", "api"]


def test_callback_rejects_missing_granted_scopes(web, monkeypatch):
    client, cfg, cache, calls = web
    state = start(client)
    class OAuth:
        def get_access_token(self, *args, **kwargs):
            cache.write_text("incomplete token")
            return {"access_token": "token", "scope": ""}
    monkeypatch.setattr(routes, "oauth_client", lambda *args: OAuth())
    assert client.get("/callback", query_string={"state": state, "code": "code"}).status_code == 400
    assert not cache.exists()


def test_app_factory_retains_signing_key(tmp_path, monkeypatch):
    from echoview.web import app as webapp
    monkeypatch.setattr(webapp, "VIEWER_HOME", str(tmp_path))
    monkeypatch.setattr(webapp, "init_config", lambda: None)
    first = webapp.create_app()
    second = webapp.create_app()
    assert first.secret_key == second.secret_key
    assert first.config["SESSION_COOKIE_HTTPONLY"]
    assert first.config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_pkce_needs_no_secret_and_legacy_stays_supported():
    cfg = dict(config(), client_secret='', auth_method='pkce')
    auth.validate_config(cfg)
    assert auth.auth_method(cfg) == 'pkce'
    assert auth.auth_method(config()) == 'authorization_code'
    with pytest.raises(ValueError):
        auth.validate_config(dict(cfg, auth_method='invalid'))
    with pytest.raises(ValueError):
        auth.validate_config(dict(cfg, auth_method='authorization_code'))


def test_pkce_state_migrates_and_restores_proof_once(tmp_path):
    import sqlite3
    path = tmp_path / 'states'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE states (state TEXT PRIMARY KEY, browser TEXT, config TEXT, expires REAL)')
    store = auth.StateStore(path)
    state = store.issue('browser', config(), verifier='private-verifier')
    assert not store.consume(state, 'other', config())
    assert auth.StateStore(path).consume(state, 'browser', config()) == 'private-verifier'
    assert not store.consume(state, 'browser', config())


def test_switch_to_pkce_removes_secret_and_requires_reauthorization(web):
    client, cfg, cache, calls = web
    pending = start(client)
    cache.write_text('old token')
    assert client.post('/configure_spotify', data=dict(config(), auth_method='pkce')).status_code == 302
    assert cfg['spotify']['auth_method'] == 'pkce'
    assert cfg['spotify']['client_secret'] == ''
    assert not cache.exists()
    assert client.get('/callback', query_string={'state': pending, 'code': 'code'}).status_code == 400


def test_saved_secret_is_not_rendered_and_blank_preserves_it(web):
    client, cfg, cache, calls = web
    cfg['spotify']['client_secret'] = 'do-not-render-this'
    assert b'do-not-render-this' not in client.get('/configure_spotify').data
    assert client.post('/configure_spotify', data=dict(config(), client_secret='', auth_method='authorization_code')).status_code == 302
    assert cfg['spotify']['client_secret'] == 'do-not-render-this'


def test_pkce_callback_restores_verifier_and_handles_spotipy_string(web, monkeypatch):
    client, cfg, cache, calls = web
    cfg['spotify'].update(auth_method='pkce', client_secret='')
    proofs = []
    class OAuth:
        def get_authorize_url(self, state):
            return 'https://accounts.spotify.com/authorize?state=' + state
        def get_access_token(self, code, check_cache):
            assert not check_cache
            return 'token-string'
        @property
        def cache_handler(self):
            return self
        def get_cached_token(self):
            return {'access_token': 'token-string', 'scope': auth.DEFAULT_SCOPE}
    def factory(cfg, path, *, verifier):
        proofs.append(verifier)
        return OAuth()
    monkeypatch.setattr(routes, 'oauth_client', factory)
    state = start(client)
    assert client.get('/callback', query_string={'state': state, 'code': 'code'}).status_code == 302
    assert len(proofs) == 2 and proofs[0] == proofs[1] and len(proofs[0]) >= 43
    assert client.get('/callback', query_string={'state': state, 'code': 'code'}).status_code == 400


def test_pinned_spotipy_pkce_protocol():
    # Other viewer tests stub Spotipy at collection time. A clean interpreter
    # verifies the actual dependency's URL, exchange and refresh contracts.
    import subprocess
    import sys
    from pathlib import Path
    result = subprocess.run([sys.executable, str(Path(__file__).parent / 'native' / 'check_spotify_pkce.py')],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


def test_concurrent_callbacks_consume_verifier_once(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    store = auth.StateStore(tmp_path / 'states')
    state = store.issue('browser', config(), verifier='proof')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: store.consume(state, 'browser', config()), range(2)))
    assert results.count('proof') == 1
    assert results.count(False) == 1
