"""Exercise the pinned Spotipy implementation without contacting Spotify."""
import base64
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import requests
from echoview.web.spotify_auth import DEFAULT_SCOPE, StateStore, oauth_client


class TokenSession(requests.Session):
    def __init__(self):
        super().__init__()
        self.calls = []

    def post(self, url, **kwargs):
        assert url == 'https://accounts.spotify.com/api/token'
        assert kwargs['timeout'] == 5
        assert 'Authorization' not in kwargs['headers']
        assert 'client_secret' not in kwargs['data']
        self.calls.append(kwargs['data'])
        response = requests.Response()
        response.status_code = 200
        token = dict(access_token='access', token_type='Bearer', expires_in=3600, scope=DEFAULT_SCOPE)
        if kwargs['data']['grant_type'] == 'authorization_code':
            token['refresh_token'] = 'refresh'
        response._content = json.dumps(token).encode()
        return response


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    cfg = dict(client_id='client', redirect_uri='http://127.0.0.1:8080/callback', auth_method='pkce')
    verifier = 'V' * 86
    session = TokenSession()
    cache = root / 'token'
    first = oauth_client(cfg, cache, verifier=verifier, requests_session=session)
    store = StateStore(root / 'states')
    state = store.issue('browser', cfg, verifier)
    query = parse_qs(urlsplit(first.get_authorize_url(state)).query)
    assert query['code_challenge_method'] == ['S256']
    assert query['code_challenge'] == [base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()]
    assert 'client_secret' not in query and 'code_verifier' not in query
    restored = StateStore(root / 'states').consume(state, 'browser', cfg)
    callback = oauth_client(cfg, cache, verifier=restored, requests_session=session)
    assert callback.get_access_token('code', check_cache=False) == 'access'
    assert session.calls[0]['code_verifier'] == verifier
    assert not store.consume(state, 'browser', cfg)
    token = json.loads(cache.read_text())
    token['expires_at'] = time.time() - 60
    cache.write_text(json.dumps(token))
    refreshed = oauth_client(cfg, cache, requests_session=session).get_cached_token()
    assert refreshed['access_token'] == 'access' and refreshed['refresh_token'] == 'refresh'
    assert session.calls[1] == dict(grant_type='refresh_token', refresh_token='refresh', client_id='client')
    assert len(session.calls) == 2
    print('Real Spotipy PKCE challenge, persisted verifier, code exchange and secret-free refresh passed.')
