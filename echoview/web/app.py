#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from flask import Flask
from echoview.config import APP_VERSION, VIEWER_HOME
from echoview.web.spotify_auth import StateStore
from echoview.utils import init_config, log_message
from echoview.web.routes import main_bp

def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    store = StateStore(os.path.join(VIEWER_HOME, ".oauth_state.sqlite3"))
    app.secret_key = store.secret()
    app.extensions["spotify_states"] = store
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
    init_config()
    app.register_blueprint(main_bp)
    return app

if __name__=="__main__":
    app = create_app()
    log_message(f"Starting EchoView Flask app version {APP_VERSION}.")
    app.run(host="0.0.0.0", port=8080, debug=False)
