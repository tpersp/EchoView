import os
import random
from fastapi import APIRouter, Body


def init_module(app, config):
    router = APIRouter()
    media_root = config.get('media_root', 'media')

    @router.get('/api/smb/folders')
    def list_folders():
        try:
            dirs = [d for d in os.listdir(media_root)
                    if os.path.isdir(os.path.join(media_root, d))]
            return {'folders': dirs}
        except Exception as e:
            return {'error': str(e)}

    @router.post('/api/smb/select')
    async def select_folders(folders: list = Body(...)):
        config['selected_folders'] = folders
        app.state.save_config(config)
        return {'status': 'ok'}

    @router.get('/api/smb/mix')
    def mix():
        selected = config.get('selected_folders', [])
        files = []
        for folder in selected:
            folder_path = os.path.join(media_root, folder)
            if os.path.isdir(folder_path):
                for name in os.listdir(folder_path):
                    full = os.path.join(folder_path, name)
                    if os.path.isfile(full):
                        files.append(os.path.join(folder, name))
        random.shuffle(files)
        return {'files': files}

    app.include_router(router)
