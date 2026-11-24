"""Bounded encoded-image staging; only QImage crosses worker boundaries."""
import os
from io import BytesIO

from PIL import Image, ImageOps
from PySide6.QtCore import QByteArray
from PySide6.QtGui import QImage

from echoview.presentation import decode_size


def read_image_data(path, policy):
    # This is encoded data, never a cache of all decoded animation frames.
    limit = min(32 * 1024 * 1024, policy['cache_budget'] // 4)
    payload = None
    try:
        with open(path, 'rb') as source:
            if os.fstat(source.fileno()).st_size <= limit:
                value = source.read(limit + 1)
                if len(value) <= limit:
                    payload = value
    except OSError:
        pass
    # Do not call Qt's image plugins from a Python worker. Their factory mutex
    # can be held by QMovie while a Python-created device tries to acquire the
    # GIL, causing lock inversion with QImageReader.size() on another thread.
    # Pillow decodes; Qt receives only a detached array of pixels.
    image = QImage()
    try:
        with Image.open(BytesIO(payload) if payload is not None else path) as source:
            width, height = decode_size(*source.size, policy)
            source.draft('RGB', (width, height))
            if source.size != (width, height):
                source.thumbnail((width, height), Image.Resampling.BILINEAR)
            oriented = ImageOps.exif_transpose(source)
            width, height = decode_size(*oriented.size, policy)
            rgba = oriented.convert('RGBA')
            if rgba.size != (width, height):
                rgba = rgba.resize((width, height), Image.Resampling.BILINEAR)
            pixels = rgba.tobytes()
            # copy() detaches storage before the Python bytes are released.
            image = QImage(pixels, width, height, width * 4, QImage.Format_RGBA8888).copy()
    except (OSError, ValueError, Image.DecompressionBombError):
        pass  # Keep the existing null-image failure path.
    gif = path.lower().endswith('.gif')
    encoded = QByteArray(payload) if gif and payload is not None and not image.isNull() else None
    return {'type': 'gif' if gif else 'static', 'path': path,
            'first_frame': image, 'image': image, 'encoded': encoded,
            'bytes': int(image.sizeInBytes()) + (encoded.size() if encoded is not None else 0)}
