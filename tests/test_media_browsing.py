import os
from pathlib import Path

from flask import Flask
import pytest

from echoview.web import media, routes


@pytest.fixture
def media_client(monkeypatch, tmp_path):
    root = tmp_path / 'media'
    root.mkdir()
    for folder in ('Photos', 'Videos', '_ignored'):
        (root / folder).mkdir()
    monkeypatch.setattr(routes, 'IMAGE_DIR', str(root))
    monkeypatch.setattr(routes, 'get_subfolders', lambda: ['Photos', 'Videos'])
    monkeypatch.setattr(routes, 'load_config', lambda: {'theme': 'dark'})
    app = Flask('echoview.web.app', template_folder='templates', static_folder='static')
    app.secret_key = 'test'
    app.register_blueprint(routes.main_bp)
    return app.test_client(), root


def test_media_navigation_does_not_scan_folder_contents(media_client, monkeypatch):
    client, root = media_client
    def fail(*a, **kw):
        pytest.fail('Opening Media must not enumerate files or inspect headers')
    monkeypatch.setattr(routes.os, 'listdir', fail)
    monkeypatch.setattr(media.os, 'scandir', fail)
    response = client.get('/upload_media')
    assert response.status_code == 200
    assert b'Photos' in response.data and b'Videos' in response.data
    assert b'<video' not in response.data and b'class="file-thumb"' not in response.data
    assert b'https://cdn' not in response.data


def test_folder_view_is_paginated_searchable_and_read_only(media_client):
    client, root = media_client
    for i in range(100):
        (root / 'Photos' / f'pic-{i:03}.jpg').write_bytes(b'unchanged')
    (root / 'Photos' / 'fake.jpg').mkdir()
    first = client.get('/media/folder?folder=Photos')
    assert first.status_code == 200
    assert first.data.count(b'class="file-thumb"') == 48
    assert b'100 files' in first.data and b'Page 1 of 3' in first.data
    assert b'pic-047.jpg' in first.data and b'pic-048.jpg' not in first.data
    second = client.get('/media/folder?folder=Photos&page=2')
    assert b'pic-048.jpg' in second.data and b'pic-000.jpg' not in second.data
    search = client.get('/media/folder?folder=Photos&q=PIC-099')
    assert b'1 files' in search.data and b'pic-099.jpg' in search.data
    assert all(p.read_bytes() == b'unchanged' for p in (root / 'Photos').glob('pic-*.jpg'))


def test_video_preview_does_not_preload_and_names_are_url_encoded(media_client):
    client, root = media_client
    (root / 'Videos' / 'one #2 & three.mp4').touch()
    response = client.get('/media/folder?folder=Videos')
    assert b'preload="none"' in response.data
    assert b'one%20%232%20&amp;%20three.mp4' in response.data


@pytest.mark.parametrize('folder', ['..', '../outside', '/tmp', '_ignored', 'a/b', 'a\\b'])
def test_folder_endpoints_reject_invalid_paths(media_client, folder):
    client, root = media_client
    for endpoint in ('/media/folder', '/media/images', '/media/videos'):
        assert client.get(endpoint, query_string={'folder': folder}).status_code == 400


def test_folder_symlink_cannot_escape_media_root(media_client, tmp_path):
    client, root = media_client
    (root / 'outside').symlink_to(tmp_path)
    assert client.get('/media/folder?folder=outside').status_code == 400


def test_unavailable_nas_reports_error_instead_of_empty_success(media_client):
    client, root = media_client
    assert client.get('/media/folder?folder=missing').status_code == 503
    assert client.get('/media/images?folder=missing').status_code == 503


def test_images_endpoint_filters_and_keeps_selected_filename(media_client, monkeypatch):
    client, root = media_client
    (root / 'Photos' / 'portrait.jpg').touch()
    (root / 'Photos' / 'landscape.jpg').touch()
    (root / 'Photos' / 'video.mp4').touch()
    monkeypatch.setattr(media, 'media_aspect_label', lambda path: Path(path).stem)
    result = client.get('/media/images?folder=Photos&aspect=portrait').get_json()
    assert result['files'] == ['portrait.jpg'] and result['total'] == 1


def test_date_sort_and_invalid_page_are_bounded(media_client):
    client, root = media_client
    for i in range(3):
        path = root / 'Photos' / f'{i}.jpg'
        path.touch()
        os.utime(path, ns=(i * 1000000000, i * 1000000000))
    result = media.folder_page(root, 'Photos', sort='date_desc', page=999)
    assert result['files'] == ['2.jpg', '1.jpg', '0.jpg']
    assert result['page'] == 1
    assert client.get('/media/images?folder=Photos&page=invalid').status_code == 200


def test_video_picker_filters_before_pagination_without_opening_media(media_client, monkeypatch):
    client,root=media_client
    for index in range(51):(root/'Videos'/f'clip-{index:03}.MP4').touch()
    for index in range(60):(root/'Videos'/f'image-{index:03}.jpg').touch()
    monkeypatch.setattr(media,'media_aspect_label',lambda *a:pytest.fail('Video picker must not inspect media headers'))
    result=client.get('/media/videos?folder=Videos').get_json()
    assert result['total']==51 and len(result['files'])==48 and result['pages']==2
    assert client.get('/media/videos?folder=Videos&page=2').get_json()['files']==['clip-048.MP4','clip-049.MP4','clip-050.MP4']
    assert client.get('/media/videos?folder=Videos&q=CLIP-050').get_json()['files']==['clip-050.MP4']
    assert client.get('/media/videos?folder=missing').status_code==503


def test_preview_endpoint_validates_paths_and_serves_cache(media_client,monkeypatch,tmp_path):
    from echoview.web import video_preview
    client,root=media_client
    source=root/'Videos'/'clip.mp4';source.write_bytes(b'unchanged')
    image=tmp_path/'cached.jpg';image.write_bytes(b'cached thumbnail')
    calls=[]
    def ready(source,directory,animated=False):calls.append((source,animated));return image,200
    monkeypatch.setattr(video_preview,'request_preview',ready)
    response=client.get('/media/video-preview?folder=Videos&file=clip.mp4&motion=1')
    assert response.status_code==200 and response.mimetype=='image/jpeg'
    assert calls==[(str(source),True)] and source.read_bytes()==b'unchanged'
    for folder,name in [('..','clip.mp4'),('Videos','../clip.mp4'),('Videos','image.jpg')]:
        assert client.get('/media/video-preview',query_string={'folder':folder,'file':name}).status_code==400
    assert client.get('/media/video-preview?folder=Videos&file=missing.mp4').status_code==503
    assert len(calls)==1
    monkeypatch.setattr(video_preview,'request_preview',lambda *a,**kw:(None,202))
    response=client.get('/media/video-preview?folder=Videos&file=clip.mp4')
    assert response.status_code==202 and response.headers['Retry-After']=='1'
    assert response.headers['Cache-Control']=='no-store'
