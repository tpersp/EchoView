"""Bounded encoded-image staging; only QImage crosses worker boundaries."""
import os

from PySide6.QtCore import QBuffer, QIODevice, QSize
from PySide6.QtGui import QImageReader

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
        pass  # QImageReader supplies the usual null image for missing files.
    buffer = None
    if payload is not None:
        buffer = QBuffer()
        buffer.setData(payload)
        buffer.open(QIODevice.ReadOnly)
    reader = QImageReader(buffer) if buffer is not None else QImageReader(path)
    reader.setAutoDetectImageFormat(True)
    reader.setAutoTransform(True)
    size = reader.size()
    width, height = decode_size(size.width(), size.height(), policy)
    if width > 0 and height > 0:
        reader.setScaledSize(QSize(width, height))
    image = reader.read()
    gif = path.lower().endswith('.gif')
    encoded = buffer.data() if gif and buffer is not None else None
    return {'type': 'gif' if gif else 'static', 'path': path,
            'first_frame': image, 'image': image, 'encoded': encoded,
            'bytes': int(image.sizeInBytes()) + (encoded.size() if encoded is not None else 0)}
