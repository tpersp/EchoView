from fastapi import APIRouter, UploadFile, File
import os


def init_module(app, config):
    media_root = config.get('media_root', 'media')
    os.makedirs(media_root, exist_ok=True)
    router = APIRouter()

    @router.post('/api/upload')
    async def upload(file: UploadFile = File(...)):
        dest = os.path.join(media_root, file.filename)
        with open(dest, 'wb') as f:
            f.write(await file.read())
        return {'status': 'ok', 'filename': file.filename}

    app.include_router(router)
