"""Spotify configuration, persistent single-use OAuth state and cache inspection."""
from contextlib import contextmanager
import hashlib
import ipaddress
import json
import os
import secrets
import sqlite3
import time
from urllib.parse import urlsplit

DEFAULT_SCOPE = "user-read-currently-playing user-read-playback-state"
STATE_TTL = 600


def validate_config(cfg):
    if not all(cfg.get(key) for key in ("client_id", "client_secret", "redirect_uri")):
        raise ValueError("Enter Client ID, Client Secret and Redirect URI.")
    try:
        if any(char.isspace() or ord(char) < 32 for char in cfg["redirect_uri"]):
            raise ValueError
        uri = urlsplit(cfg["redirect_uri"])
        port = uri.port
        loopback = False
        try:
            loopback = ipaddress.ip_address(uri.hostname or "").is_loopback
        except ValueError:
            pass
        if (not uri.hostname or uri.hostname.lower() == "localhost" or uri.username
                or uri.password or uri.fragment or uri.query or uri.path != "/callback"
                or (port is not None and port == 0)
                or (uri.scheme != "https" and not (uri.scheme == "http" and loopback))):
            raise ValueError
    except ValueError:
        raise ValueError("Use an HTTPS /callback URL, or HTTP with an explicit loopback IP; localhost and HTTP LAN addresses are not supported.") from None
    if not set(DEFAULT_SCOPE.split()).issubset(str(cfg.get("scope", DEFAULT_SCOPE)).split()):
        raise ValueError("Both user-read-currently-playing and user-read-playback-state scopes are required.")


def fingerprint(cfg):
    return hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()


class StateStore:
    """SQLite transactions prevent callback replay across processes and restarts."""
    def __init__(self, path):
        self.path = os.fspath(path)
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(fd)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS states (state TEXT PRIMARY KEY, browser TEXT, config TEXT, expires REAL)")
            db.execute("INSERT OR IGNORE INTO settings VALUES ('secret', ?)", (secrets.token_hex(32),))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def secret(self):
        with self.connect() as db:
            return db.execute("SELECT value FROM settings WHERE name='secret'").fetchone()[0]

    def issue(self, browser, cfg):
        state = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute("DELETE FROM states WHERE expires < ?", (time.time(),))
            db.execute("INSERT INTO states VALUES (?, ?, ?, ?)",
                       (hashlib.sha256(state.encode()).hexdigest(), browser, fingerprint(cfg), time.time() + STATE_TTL))
        return state

    def consume(self, state, browser, cfg):
        digest = hashlib.sha256(state.encode()).hexdigest()
        with self.connect() as db:
            result = db.execute("DELETE FROM states WHERE state=? AND browser=? AND config=? AND expires>=?",
                                (digest, browser, fingerprint(cfg), time.time()))
            return result.rowcount == 1


def cached_status(cfg, path):
    """Never refresh or make network calls just to render a page."""
    try:
        validate_config(cfg)
    except ValueError as exc:
        return str(exc)
    try:
        with open(path) as source:
            token = json.load(source)
        if not isinstance(token, dict) or not token.get("access_token"):
            return "Invalid token cache — authorize again."
        if not set(cfg.get("scope", DEFAULT_SCOPE).split()).issubset(str(token.get("scope", "")).split()):
            return "Token permissions are incomplete — authorize again."
        expires = float(token.get("expires_at", 0))
        if expires <= time.time():
            return "Token expired; refresh available. Check connection." if token.get("refresh_token") else "Token expired — authorize again."
        return "Cached token valid; connection not checked."
    except FileNotFoundError:
        return "Credentials saved — authorize Spotify."
    except (OSError, ValueError, TypeError):
        return "Token cache unreadable — authorize again."


def oauth_client(cfg, cache_path):
    from spotipy.oauth2 import SpotifyOAuth
    validate_config(cfg)
    os.makedirs(os.path.dirname(os.path.abspath(cache_path)), exist_ok=True)
    return SpotifyOAuth(client_id=cfg["client_id"], client_secret=cfg["client_secret"],
                        redirect_uri=cfg["redirect_uri"], scope=cfg.get("scope", DEFAULT_SCOPE),
                        cache_path=cache_path, open_browser=False, requests_timeout=5)
