import os
import threading
import time
from fastapi import APIRouter, Request, Body
import spotipy
from spotipy.oauth2 import SpotifyOAuth


def init_module(app, config):
    router = APIRouter()
    spotify_conf = config.setdefault('spotify', {})
    spotify_conf.setdefault('tokens', {})
    spotify_conf.setdefault('fallback', '')

    status = {
        'playing': False,
        'artist': '',
        'title': '',
        'album_image': '',
        'progress_ms': 0,
        'duration_ms': 0,
    }

    def save_conf():
        app.state.save_config(config)

    def get_auth():
        return SpotifyOAuth(
            scope='user-read-playback-state',
            client_id=os.getenv('SPOTIPY_CLIENT_ID'),
            client_secret=os.getenv('SPOTIPY_CLIENT_SECRET'),
            redirect_uri=os.getenv('SPOTIPY_REDIRECT_URI') or 'http://localhost:8000/api/spotify/callback'
        )

    def get_spotify():
        tokens = spotify_conf.get('tokens')
        if not tokens:
            return None
        auth = get_auth()
        auth.cache_handler.save_token_to_cache(tokens)
        token_info = auth.cache_handler.get_cached_token()
        if not token_info:
            return None
        if auth.is_token_expired(token_info):
            token_info = auth.refresh_access_token(token_info['refresh_token'])
            spotify_conf['tokens'] = token_info
            save_conf()
        return spotipy.Spotify(auth=token_info['access_token'])

    def poll():
        while True:
            sp = get_spotify()
            if sp:
                try:
                    current = sp.current_playback()
                    if current and current.get('item'):
                        item = current['item']
                        status.update({
                            'playing': current['is_playing'],
                            'artist': ', '.join(a['name'] for a in item['artists']),
                            'title': item['name'],
                            'album_image': item['album']['images'][0]['url'] if item['album']['images'] else '',
                            'progress_ms': current['progress_ms'],
                            'duration_ms': item['duration_ms'],
                        })
                    else:
                        status['playing'] = False
                except Exception as e:
                    status['playing'] = False
                    status['error'] = str(e)
            else:
                status['playing'] = False
            time.sleep(5)

    threading.Thread(target=poll, daemon=True).start()

    @router.get('/api/spotify/auth_url')
    def auth_url():
        url = get_auth().get_authorize_url()
        return {'url': url}

    @router.get('/api/spotify/callback')
    def callback(request: Request):
        code = request.query_params.get('code')
        if not code:
            return {'error': 'missing code'}
        auth = get_auth()
        token_info = auth.get_access_token(code, as_dict=True)
        spotify_conf['tokens'] = token_info
        save_conf()
        return {'status': 'ok'}

    @router.get('/api/spotify/status')
    def get_status():
        return {'status': status, 'fallback': spotify_conf.get('fallback', '')}

    @router.post('/api/spotify/fallback')
    def set_fallback(data: dict = Body(...)):
        spotify_conf['fallback'] = data.get('file', '')
        save_conf()
        return {'status': 'ok'}

    app.include_router(router)
