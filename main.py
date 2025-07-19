from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import importlib
import os
import json
from updater.update import perform_update

app = FastAPI()

# Persistent config
CONFIG_PATH = 'config/settings.json'
def load_config():
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'w') as f:
            json.dump({}, f)
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f)

config = load_config()

# Modular loader
MODULES_PATH = 'modules'
loaded_modules = {}
for module_name in os.listdir(MODULES_PATH):
    module_path = os.path.join(MODULES_PATH, module_name)
    if os.path.isdir(module_path) and os.path.exists(os.path.join(module_path, '__init__.py')):
        mod = importlib.import_module(f'modules.{module_name}')
        if hasattr(mod, 'init_module'):
            mod.init_module(app, config)
        loaded_modules[module_name] = mod

# Mount static files for frontend
app.mount('/static', StaticFiles(directory='static'), name='static')

@app.get('/')
def root():
    return {'message': 'EchoView server running'}


@app.post('/update')
def update_repo():
    """Fetch latest version from GitHub and overwrite local changes."""
    perform_update()
    return {'status': 'updated'}
