import os
from fastapi import APIRouter, HTTPException


def init_module(app, config):
    router = APIRouter()
    media_root = config.get('media_root', 'media')

    config.setdefault('current_media', '')

    @router.get('/api/media/list')
    def list_media():
        files = []
        for root, _, filenames in os.walk(media_root):
            for name in filenames:
                rel = os.path.relpath(os.path.join(root, name), media_root)
                files.append(rel)
        return {'files': files}

    @router.post('/api/display/{path:path}')
    def set_display(path: str):
        if path.startswith('http://') or path.startswith('https://'):
            config['current_media'] = path
            app.state.save_config(config)
            return {'status': 'ok'}

        normalized = os.path.normpath(path)
        full = os.path.join(media_root, normalized)
        if not os.path.isfile(full):
            raise HTTPException(status_code=404, detail='File not found')
        if os.path.commonpath([os.path.abspath(full), os.path.abspath(media_root)]) != os.path.abspath(media_root):
            raise HTTPException(status_code=400, detail='Invalid path')
        config['current_media'] = normalized
        app.state.save_config(config)
        return {'status': 'ok'}

    @router.get('/api/display')
    def get_display():
        return {'file': config.get('current_media', '')}

    app.include_router(router)
