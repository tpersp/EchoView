from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import subprocess

from flask import Flask
import pytest

from echoview import displays, presets
from echoview.web import routes


@pytest.fixture
def workflow(tmp_path, monkeypatch):
    root = tmp_path / 'media'
    (root / 'Photos').mkdir(parents=True)
    (root / 'Videos').mkdir()
    (root / 'Photos' / 'one #2.jpg').write_bytes(b'untouched photo')
    (root / 'Videos' / 'clip.mp4').write_bytes(b'untouched video')
    cfg = {'theme': 'dark', 'resource_profile': 'pi3',
           'spotify': {'client_secret': 'never-in-a-preset'},
           'displays': {name: displays.default_display(name) for name in ('HDMI-1', 'HDMI-2')}}
    cfg['displays']['HDMI-1'].update(video_volume=35, video_mute=True, safe_area={'left': 5},
                                     mixed_folders=['Photos'], video_category='Videos')
    saves, restarts = [], []
    def save(value):
        copied = deepcopy(value)
        saves.append(copied)
        cfg.clear()
        cfg.update(copied)
    monkeypatch.setattr(routes, 'apply_live_settings', lambda cfg,names: True)
    monkeypatch.setattr(routes, 'load_config', lambda: cfg)
    monkeypatch.setattr(routes, 'save_config', save)
    monkeypatch.setattr(routes, 'IMAGE_DIR', str(root))
    monkeypatch.setattr(routes, 'get_subfolders', lambda: ['Photos', 'Videos'])
    monkeypatch.setattr(routes, 'detect_monitors_extended', lambda: {})
    monkeypatch.setattr(routes, 'get_hostname', lambda: 'fixture')
    monkeypatch.setattr(routes, 'get_ip_address', lambda: 'fixture')
    monkeypatch.setattr(routes, 'get_pi_model', lambda: 'fixture')
    monkeypatch.setattr(routes.subprocess, 'run', lambda args, **kw: restarts.append((args, kw)) or SimpleNamespace(returncode=0))
    app = Flask('echoview.web.app', template_folder='templates', static_folder='static')
    app.secret_key = 'test'
    app.register_blueprint(routes.main_bp)
    return app.test_client(), cfg, saves, restarts, root


@pytest.mark.parametrize('folder,filename,mode', [('Photos', 'one #2.jpg', 'specific_image'), ('Videos', 'clip.mp4', 'videos')])
def test_play_file_changes_only_target_and_never_media(workflow, folder, filename, mode):
    client, cfg, saves, restarts, root = workflow
    before = deepcopy(cfg)
    path = root / folder / filename
    metadata, content = path.stat(), path.read_bytes()
    response = client.post('/media/play', data={'display': 'HDMI-1', 'selection': 'file',
                                               'folder': folder, 'filename': filename},
                           headers={'Accept': 'application/json'})
    assert response.status_code == 200 and response.json['saved'] is True
    selected = cfg['displays']['HDMI-1']
    assert selected['mode'] == mode
    assert selected['specific_image' if mode == 'specific_image' else 'specific_video'] == filename
    assert selected['video_volume'] == 35 and selected['video_mute'] is True
    assert selected['safe_area'] == before['displays']['HDMI-1']['safe_area']
    assert cfg['displays']['HDMI-2'] == before['displays']['HDMI-2']
    assert cfg['spotify'] == before['spotify'] and cfg['resource_profile'] == 'pi3'
    assert path.read_bytes() == content and path.stat().st_mtime_ns == metadata.st_mtime_ns
    assert len(saves) == len(restarts) == 1
    assert restarts[0][1]['timeout'] == 20


def test_play_folder_clears_single_video_but_keeps_other_preferences(workflow):
    client, cfg, saves, restarts, root = workflow
    cfg['displays']['HDMI-1']['specific_video'] = 'clip.mp4'
    response = client.post('/media/play', data={'display': 'HDMI-1', 'selection': 'folder_videos', 'folder': 'Videos'})
    assert response.status_code == 302
    assert cfg['displays']['HDMI-1']['specific_video'] == ''
    assert cfg['displays']['HDMI-1']['mixed_folders'] == ['Photos']


@pytest.mark.parametrize('data', [
    {'display': 'unknown', 'selection': 'file', 'folder': 'Photos', 'filename': 'one #2.jpg'},
    {'display': 'HDMI-1', 'selection': 'file', 'folder': '..', 'filename': 'one #2.jpg'},
    {'display': 'HDMI-1', 'selection': 'file', 'folder': 'Photos', 'filename': '../secret.jpg'},
    {'display': 'HDMI-1', 'selection': 'file', 'folder': 'Photos', 'filename': 'missing.jpg'},
    {'display': 'HDMI-1', 'selection': 'folder_images', 'folder': 'missing'},
])
def test_bad_media_selection_never_saves_or_restarts(workflow, data):
    client, cfg, saves, restarts, root = workflow
    before = deepcopy(cfg)
    response = client.post('/media/play', data=data, headers={'Accept': 'application/json'})
    assert response.status_code in (400, 404) and response.json['saved'] is False
    assert cfg == before and not saves and not restarts


def test_save_failure_never_restarts_viewer(workflow, monkeypatch):
    client, cfg, saves, restarts, root = workflow
    before = deepcopy(cfg)
    def fail(*args):
        raise OSError('disk full')
    monkeypatch.setattr(routes, 'save_config', fail)
    response = client.post('/media/play', data={'display': 'HDMI-1', 'selection': 'folder_images', 'folder': 'Photos'}, headers={'Accept': 'application/json'})
    assert response.status_code == 503 and response.json['saved'] is False
    assert cfg == before and not restarts


def test_restart_failure_truthfully_preserves_saved_selection(workflow, monkeypatch):
    client, cfg, saves, restarts, root = workflow
    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired('systemctl', 20)
    monkeypatch.setattr(routes.subprocess, 'run', fail)
    response = client.post('/media/play', data={'display': 'HDMI-1', 'selection': 'folder_images', 'folder': 'Photos'}, headers={'Accept': 'application/json'})
    assert response.status_code == 503 and response.json['saved'] is True
    assert cfg['displays']['HDMI-1']['image_category'] == 'Photos'


def test_presets_save_restore_and_delete_without_changing_physical_settings(workflow):
    client, cfg, saves, restarts, root = workflow
    original = deepcopy(cfg['displays']['HDMI-1'])
    assert client.post('/display/presets', data={'action': 'save', 'name': 'Evening'}).status_code == 302
    assert not restarts
    preset = cfg['display_presets']['Evening']
    assert 'client_secret' not in str(preset) and 'safe_area' not in str(preset)
    client.post('/display/presets', data={'action': 'apply', 'name': 'Evening'})
    assert not restarts
    cfg['displays']['HDMI-1'].update(mode='videos', specific_video='clip.mp4', safe_area={'left': 12}, output_mode='1920x1080@60')
    cfg['resource_profile'] = 'standard'
    assert client.post('/display/presets', data={'action': 'apply', 'name': 'Evening'}).status_code == 302
    assert cfg['displays']['HDMI-1']['mode'] == original['mode']
    assert cfg['displays']['HDMI-1']['specific_video'] == ''
    assert cfg['displays']['HDMI-1']['safe_area'] == {'left': 12}
    assert cfg['displays']['HDMI-1']['output_mode'] == '1920x1080@60'
    assert cfg['resource_profile'] == 'standard'
    assert len(restarts) == 1
    client.post('/display/presets', data={'action': 'apply', 'name': 'Evening'})
    assert len(restarts) == 1  # Applying an already-active preset is a no-op.
    client.post('/display/presets', data={'action': 'delete', 'name': 'Evening'})
    assert not cfg['display_presets'] and len(restarts) == 1


@pytest.mark.parametrize('name', ['', 'x' * 49, 'bad\nname'])
def test_invalid_preset_name_is_not_saved(workflow, name):
    client, cfg, saves, restarts, root = workflow
    client.post('/display/presets', data={'action': 'save', 'name': name})
    assert not saves and not restarts


def test_preset_names_cannot_silently_overwrite_and_count_is_bounded(workflow):
    client, cfg, saves, restarts, root = workflow
    client.post('/display/presets', data={'action': 'save', 'name': 'Evening'})
    client.post('/display/presets', data={'action': 'save', 'name': 'evening'})
    assert len(saves) == 1
    cfg['display_presets'] = {str(i): presets.snapshot(cfg) for i in range(20)}
    client.post('/display/presets', data={'action': 'save', 'name': 'Extra'})
    assert len(saves) == 1


def test_switching_mode_preserves_other_modes_and_other_display(workflow):
    client, cfg, saves, restarts, root = workflow
    other = deepcopy(cfg['displays']['HDMI-2'])
    cfg['displays']['HDMI-1']['specific_video'] = 'clip.mp4'
    client.post('/', data={'action': 'update_displays', 'HDMI-1_mode': 'calibration'})
    selected = cfg['displays']['HDMI-1']
    assert selected['mixed_folders'] == ['Photos']
    assert selected['video_category'] == 'Videos' and selected['specific_video'] == 'clip.mp4'
    assert cfg['displays']['HDMI-2'] == other


def test_unchanged_form_does_not_interrupt_playback(workflow):
    client, cfg, saves, restarts, root = workflow
    response = client.post('/', data={'action': 'update_displays'})
    assert response.status_code == 302 and not saves and not restarts


def test_preset_restore_is_pure_and_rejects_unmatched_displays():
    cfg = {'displays': {'HDMI-1': {'mode': 'random_image', 'safe_area': {'left': 3}}}}
    before = deepcopy(cfg)
    restored = presets.restore(cfg, {'format': 1, 'displays': {'HDMI-1': {'mode': 'videos', 'safe_area': {'left': 99}}}})
    assert cfg == before and restored['displays']['HDMI-1']['safe_area'] == {'left': 3}
    with pytest.raises(ValueError, match='no matching'):
        presets.restore(cfg, {'format': 1, 'displays': {'HDMI-9': {'mode': 'videos'}}})


def test_preset_handles_known_hdmi_alias_without_changing_output():
    cfg = {'displays': {'HDMI-A-1': {'mode': 'random_image', 'output_mode': 'auto'}}}
    result = presets.restore(cfg, {'format': 1, 'displays': {'HDMI-1': {'mode': 'videos', 'output_mode': 'bad'}}})
    assert result['displays']['HDMI-A-1'] == {'mode': 'videos', 'output_mode': 'auto'}


def test_changing_video_folder_clears_stale_individual_selection(workflow):
    client, cfg, saves, restarts, root = workflow
    cfg['displays']['HDMI-1'].update(mode='videos', specific_video='clip.mp4')
    client.post('/', data={'action': 'update_displays', 'HDMI-1_mode': 'videos',
                            'HDMI-1_video_category': 'Photos', 'HDMI-1_specific_video': 'clip.mp4'})
    assert cfg['displays']['HDMI-1']['specific_video'] == ''


def test_quick_play_rejects_symlink_escape(workflow, tmp_path):
    client, cfg, saves, restarts, root = workflow
    outside = tmp_path / 'private.mp4'
    outside.touch()
    (root / 'Videos' / 'escape.mp4').symlink_to(outside)
    response = client.post('/media/play', data={'display': 'HDMI-1', 'selection': 'file',
                                               'folder': 'Videos', 'filename': 'escape.mp4'},
                           headers={'Accept': 'application/json'})
    assert response.status_code == 400 and not saves and not restarts


def test_missing_nas_folder_remains_selected_in_display_form(workflow, monkeypatch):
    client, cfg, saves, restarts, root = workflow
    cfg['displays']['HDMI-1'].update(image_category='Missing photos', video_category='Missing videos')
    monkeypatch.setattr(routes, 'get_subfolders', lambda: [])
    response = client.get('/')
    assert b'value="Missing photos" selected' in response.data
    assert b'value="Missing videos" selected' in response.data


def test_mixed_folders_round_trip_names_with_commas_and_keep_order(workflow):
    client, cfg, saves, restarts, root = workflow
    client.post('/', data={'action': 'update_displays', 'HDMI-1_mode': 'mixed',
                           'HDMI-1_mixed_order': '["Trips, 2026", "Photos"]'})
    assert cfg['displays']['HDMI-1']['mixed_folders'] == ['Trips, 2026', 'Photos']


def test_malformed_mixed_folder_order_never_saves(workflow):
    client, cfg, saves, restarts, root = workflow
    response = client.post('/', data={'action': 'update_displays', 'HDMI-1_mode': 'mixed',
                                      'HDMI-1_mixed_order': '[null]'})
    assert response.status_code == 400 and not saves and not restarts


def test_older_mixed_folder_forms_still_work(workflow):
    client, cfg, saves, restarts, root = workflow
    client.post('/', data={'action': 'update_displays', 'HDMI-1_mode': 'mixed',
                           'HDMI-1_mixed_order': 'Photos,Videos'})
    assert cfg['displays']['HDMI-1']['mixed_folders'] == ['Photos', 'Videos']


def test_schedule_editor_and_device_clock_are_available(workflow):
    client, cfg, saves, restarts, root = workflow
    response = client.get('/')
    assert b'>Scheduled playback</option>' in response.data
    assert b'class="schedule-editor"' in response.data
    assert b'06:00 / 14:00 / 18:00' in response.data
    clock = client.get('/schedule/clock')
    assert clock.status_code == 200 and 'no-store' in clock.headers['Cache-Control']
    assert 0 <= clock.json['seconds'] < 86400
    assert not restarts


def test_schedule_save_is_canonical_and_unchanged_apply_is_noop(workflow):
    import json
    client, cfg, saves, restarts, root = workflow
    form = {'action': 'update_displays', 'HDMI-1_mode': 'scheduled', 'HDMI-1_schedule': json.dumps([
        {'time': '18:00', 'folders': ['Videos'], 'media': 'videos'},
        {'time': '06:00', 'folders': ['Photos', 'Missing NAS folder'], 'shuffle': True}]),
        'HDMI-1_video_mute': '1', 'HDMI-1_video_volume': '25'}
    response = client.post('/', data=form)
    assert response.status_code == 302
    assert cfg['displays']['HDMI-1']['mode'] == 'scheduled'
    assert [entry['time'] for entry in cfg['displays']['HDMI-1']['schedule']] == ['06:00', '18:00']
    assert cfg['displays']['HDMI-1']['video_volume'] == 25
    assert cfg['displays']['HDMI-1']['video_category'] == 'Videos'
    assert cfg['displays']['HDMI-1']['safe_area'] == {'left': 5}
    assert len(restarts) == 1
    client.post('/', data=form)
    assert len(restarts) == 1
    client.post('/', data={'action': 'update_displays', 'HDMI-1_mode': 'calibration', 'HDMI-1_schedule': 'invalid'})
    assert len(cfg['displays']['HDMI-1']['schedule']) == 2


@pytest.mark.parametrize('value', ['[]', 'invalid', '[{"time":"18:00","folders":[]}]'])
def test_invalid_schedule_never_saves_or_restarts(workflow, value):
    client, cfg, saves, restarts, root = workflow
    before = deepcopy(cfg)
    response = client.post('/', data={'action': 'update_displays', 'HDMI-1_mode': 'scheduled', 'HDMI-1_schedule': value})
    assert response.status_code == 400
    assert not saves and not restarts and cfg == before


def test_bad_schedule_on_second_display_does_not_mutate_first(workflow):
    client, cfg, saves, restarts, root = workflow
    before = deepcopy(cfg)
    response = client.post('/', data={'action': 'update_displays', 'HDMI-1_mode': 'calibration',
                                      'HDMI-2_mode': 'scheduled', 'HDMI-2_schedule': '[]'})
    assert response.status_code == 400 and cfg == before and not saves and not restarts


def test_smooth_progress_preference_saves_and_survives_presets(workflow):
    client, cfg, saves, restarts, root = workflow
    form = {'action': 'update_displays', 'HDMI-1_mode': 'spotify',
            'HDMI-1_spotify_show_progress': '1', 'HDMI-1_spotify_smooth_progress': '1'}
    assert client.post('/', data=form).status_code == 302
    assert cfg['displays']['HDMI-1']['spotify_smooth_progress'] is True
    preset = presets.snapshot(cfg)
    del form['HDMI-1_spotify_smooth_progress']
    assert client.post('/', data=form).status_code == 302
    assert cfg['displays']['HDMI-1']['spotify_smooth_progress'] is False
    assert presets.restore(cfg, preset)['displays']['HDMI-1']['spotify_smooth_progress'] is True


def test_spotify_time_toggle_saves_presets_and_preserves_cached_forms(workflow):
    client, cfg, saves, restarts, root = workflow
    form = {'action': 'update_displays', 'HDMI-1_mode': 'spotify',
            'HDMI-1_spotify_time_present': '1', 'HDMI-1_spotify_show_time': '1'}
    assert client.post('/', data=form).status_code == 302
    assert cfg['displays']['HDMI-1']['spotify_show_time'] is True
    snapshot = presets.snapshot(cfg)
    del form['HDMI-1_spotify_time_present']
    del form['HDMI-1_spotify_show_time']
    assert client.post('/', data=form).status_code == 302
    assert cfg['displays']['HDMI-1']['spotify_show_time'] is True
    form['HDMI-1_spotify_time_present'] = '1'
    assert client.post('/', data=form).status_code == 302
    assert cfg['displays']['HDMI-1']['spotify_show_time'] is False
    assert presets.restore(cfg, snapshot)['displays']['HDMI-1']['spotify_show_time'] is True


@pytest.mark.parametrize("mode", ["gradient", "blurred"])
def test_spotify_background_saved_live_keys_and_legacy_forms_and_presets(workflow,mode):
    client,cfg,saves,restarts,root=workflow
    form={'action':'update_displays','HDMI-1_mode':'spotify','HDMI-1_spotify_background_mode':mode,'HDMI-1_spotify_background_dim':'40'}
    assert client.post('/',data=form).status_code==302
    snapshot=presets.snapshot(cfg)
    assert cfg['displays']['HDMI-1']['spotify_background_dim']==40
    assert client.post('/',data={'action':'update_displays','HDMI-1_mode':'spotify'}).status_code==302
    assert cfg['displays']['HDMI-1']['spotify_background_mode']==mode
    cfg['displays']['HDMI-1']['spotify_background_mode']='black'
    assert presets.restore(cfg,snapshot)['displays']['HDMI-1']['spotify_background_mode']==mode
    del snapshot['displays']['HDMI-1']['spotify_background_mode']
    del snapshot['displays']['HDMI-1']['spotify_background_dim']
    restored=presets.restore(cfg,snapshot)['displays']['HDMI-1']
    assert restored['spotify_background_mode']=='black' and restored['spotify_background_dim']==65


@pytest.mark.parametrize('key,value', [('mode','animated'),('dim','-1'),('dim','96'),('dim','bad')])
def test_spotify_background_invalid_settings_never_save(workflow,key,value):
    client,cfg,saves,restarts,root=workflow
    before=deepcopy(cfg)
    form={'action':'update_displays','HDMI-1_mode':'spotify','HDMI-1_spotify_background_'+key:value}
    assert client.post('/',data=form).status_code==400
    assert not saves and not restarts and cfg==before


def test_spotify_layout_saved_in_presets_and_validated(workflow):
    client, cfg, saves, restarts, root = workflow
    form = {'action': 'update_displays', 'HDMI-1_mode': 'spotify', 'HDMI-1_spotify_layout': 'album_card'}
    assert client.post('/', data=form).status_code == 302
    assert cfg['displays']['HDMI-1']['spotify_layout'] == 'album_card'
    preset = presets.snapshot(cfg)
    cfg['displays']['HDMI-1']['spotify_layout'] = 'poster'
    assert presets.restore(cfg,preset)['displays']['HDMI-1']['spotify_layout'] == 'album_card'
    form['HDMI-1_spotify_layout'] = 'bad-layout'
    before = deepcopy(cfg)
    assert client.post('/', data=form).status_code == 400
    assert cfg == before


def test_spotify_device_toggle_saves_and_survives_presets(workflow):
    client, cfg, saves, restarts, root = workflow
    form = {'action':'update_displays', 'HDMI-1_mode':'spotify', 'HDMI-1_spotify_show_device':'1'}
    assert client.post('/',data=form).status_code == 302
    assert cfg['displays']['HDMI-1']['spotify_show_device'] is True
    preset = presets.snapshot(cfg)
    del form['HDMI-1_spotify_show_device']
    assert client.post('/',data=form).status_code == 302
    assert cfg['displays']['HDMI-1']['spotify_show_device'] is False
    assert presets.restore(cfg,preset)['displays']['HDMI-1']['spotify_show_device'] is True


def test_old_preset_keeps_device_line_off(workflow):
    client, cfg, saves, restarts, root = workflow
    preset = presets.snapshot(cfg)
    for settings in preset['displays'].values():
        settings.pop('spotify_show_device', None)
    cfg['displays']['HDMI-1']['spotify_show_device'] = True
    assert presets.restore(cfg,preset)['displays']['HDMI-1']['spotify_show_device'] is False


def test_visual_apply_is_live_but_media_change_restarts(workflow,monkeypatch):
    client,cfg,saves,restarts,root=workflow
    cfg['displays']['HDMI-1']['mode']='spotify'
    previous=deepcopy(cfg)
    updated=deepcopy(cfg); updated['displays']['HDMI-1']['spotify_font_size']=24
    applied=[]
    monkeypatch.setattr(routes,'apply_live_settings',lambda cfg,names:applied.extend(names) or True)
    result,status=routes._save_display_settings(updated,previous)
    assert status==200 and 'kept running' in result['message']
    assert applied==['HDMI-1'] and not restarts
    changed=deepcopy(updated); changed['displays']['HDMI-1']['mode']='videos'
    assert routes._save_display_settings(changed,updated)[1]==200
    assert len(restarts)==1


def test_unconfirmed_visual_apply_keeps_save_and_never_restarts(workflow,monkeypatch):
    client,cfg,saves,restarts,root=workflow
    cfg['displays']['HDMI-1']['mode']='spotify'
    updated=deepcopy(cfg); updated['displays']['HDMI-1']['spotify_font_size']=24
    monkeypatch.setattr(routes,'apply_live_settings',lambda cfg,names:False)
    result,status=routes._save_display_settings(updated,cfg)
    assert status==503 and result['saved'] is True
    assert 'could not be confirmed' in result['message']
    assert cfg['displays']['HDMI-1']['spotify_font_size']==24 and not restarts


def test_visual_save_failure_never_signals_viewer(workflow,monkeypatch):
    client,cfg,saves,restarts,root=workflow
    cfg['displays']['HDMI-1']['mode']='spotify'
    updated=deepcopy(cfg); updated['displays']['HDMI-1']['spotify_font_size']=24
    def fail(cfg): raise OSError('full')
    monkeypatch.setattr(routes,'save_config',fail)
    monkeypatch.setattr(routes,'apply_live_settings',lambda *args:pytest.fail('must not apply unsaved settings'))
    result,status=routes._save_display_settings(updated,cfg)
    assert status==503 and result['saved'] is False and not restarts
