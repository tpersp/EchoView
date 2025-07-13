import os
import requests
import time

class SpotifyAPI:
    def __init__(self, client_id, client_secret, refresh_token):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.access_token = None
        self.token_expiry = 0

    def refresh_access_token(self):
        url = "https://accounts.spotify.com/api/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        response = requests.post(url, data=data)
        if response.status_code == 200:
            token_info = response.json()
            self.access_token = token_info["access_token"]
            self.token_expiry = time.time() + token_info.get("expires_in", 3600)
        else:
            raise Exception(f"Spotify token refresh failed: {response.text}")

    def get_current_playback(self):
        if not self.access_token or time.time() > self.token_expiry:
            self.refresh_access_token()
        headers = {"Authorization": f"Bearer {self.access_token}"}
        response = requests.get("https://api.spotify.com/v1/me/player/currently-playing", headers=headers)
        if response.status_code == 200:
            return response.json()
        return None
