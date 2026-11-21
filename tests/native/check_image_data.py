"""Native image staging checks using only temporary synthetic media."""
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PIL import Image
from PySide6.QtCore import QCoreApplication
from echoview.image_data import read_image_data
from echoview.presentation import resource_settings

app = QCoreApplication([])
with tempfile.TemporaryDirectory(prefix='echoview-image-data-') as directory:
    root = Path(directory)
    policy = resource_settings('standard', {})
    for name in ('image.png', 'animation.GIF'):
        path = root / name
        Image.new('RGB', (32, 24), 'red').save(path)
        data = read_image_data(str(path), policy)
        assert not data['image'].isNull()
        assert data['image'].pixelColor(0, 0).name() == '#ff0000'
        if name.endswith('GIF'):
            assert data['encoded'].size() == path.stat().st_size
            assert data['bytes'] == data['image'].sizeInBytes() + path.stat().st_size
            # An intentionally tiny budget forces the original file path,
            # preserving playback of files above the encoded staging limit.
            large = read_image_data(str(path), dict(policy, cache_budget=16))
            assert large['encoded'] is None and not large['image'].isNull()
        else:
            assert data['encoded'] is None
            assert data['bytes'] == data['image'].sizeInBytes()
    broken = root / 'broken.gif'
    broken.write_bytes(b'not an image')
    for path in (broken, root / 'missing.gif'):
        assert read_image_data(str(path), policy)['image'].isNull()
    oriented = root / 'oriented.jpg'
    exif = Image.Exif()
    exif[274] = 6
    Image.new('RGB', (80, 40), 'red').save(oriented, exif=exif)
    rotated = read_image_data(str(oriented), policy)['image']
    assert (rotated.width(), rotated.height()) == (40, 80)
    transparent = root / 'transparent.png'
    Image.new('RGBA', (16, 16), (20, 40, 60, 80)).save(transparent)
    pixel = read_image_data(str(transparent), policy)['image'].pixelColor(0, 0)
    assert (pixel.red(), pixel.green(), pixel.blue(), pixel.alpha()) == (20, 40, 60, 80)
    scaled = read_image_data(str(transparent), dict(policy, decode_pixels=64, decode_side=8))['image']
    assert scaled.width() == scaled.height() == 8
print('Image staging: static/GIF decode, byte accounting, oversized fallback, corrupt/missing files passed.')
