from copy import deepcopy
from types import SimpleNamespace
import subprocess
from pathlib import Path

from flask import Flask
import pytest

from echoview import branches, presentation, updates, utils
from echoview.web import routes


@pytest.fixture
def settings_client(monkeypatch):
    cfg={'theme':'dark', 'gui':{'background_blur_radius':7}, 'resource_profile':'standard',
         'displays': {'HDMI-1': {'mode':'calibration','safe_area':{'left':5}}, 'Composite-1':{'mode':'random_image'}}}
    saves=[]
    monkeypatch.setattr(routes,'load_config',lambda:cfg)
    monkeypatch.setattr(routes,'save_config',lambda value:saves.append(deepcopy(value)))
    monkeypatch.setattr(routes,'branch_options',lambda repo,selected,remote=False:{'branches':['dev','main',selected], 'selected':selected,'available':False})
    app=Flask(__name__,template_folder=str(Path(routes.__file__).parent/'templates'))
    app.secret_key='test';app.register_blueprint(routes.main_bp)
    return app.test_client(),cfg,saves


def test_settings_places_device_policy_and_branch_controls_together(settings_client):
    client,cfg,saves=settings_client
    response=client.get('/settings')
    assert response.status_code==200
    assert b'name="resource_profile"' in response.data
    assert b'GIFs and videos play normally' in response.data
    assert b'name="update_branch"' in response.data
    assert b'Refresh branches' in response.data
    assert not saves


def test_save_branch_preserves_other_settings_and_never_updates(settings_client,monkeypatch):
    client,cfg,saves=settings_client
    before=deepcopy(cfg)
    monkeypatch.setattr(updates,'update',lambda *a,**kw:pytest.fail('Saving a branch must not update'))
    monkeypatch.setattr(routes.subprocess,'run',lambda *a,**kw:pytest.fail('Branch save must not run processes'))
    assert client.post('/settings',data={'action':'update_branch','update_branch':'feature/display'}).status_code==302
    assert cfg==dict(before,update_branch='feature/display')
    assert saves[-1]['update_branch']=='feature/display'


@pytest.mark.parametrize('branch',['--help','dev~1','origin/main^{commit}','../main','a//b','a.lock','a/.hidden','main\nother',''])
def test_invalid_branch_never_saved(settings_client,branch):
    client,cfg,saves=settings_client
    assert client.post('/settings',data={'action':'update_branch','update_branch':branch}).status_code==400
    assert not saves


def test_device_profile_preserves_screen_preferences(settings_client,monkeypatch):
    client,cfg,saves=settings_client
    before=deepcopy(cfg['displays']);calls=[]
    monkeypatch.setattr(routes.subprocess,'run',lambda cmd,**kw:calls.append(cmd))
    response=client.post('/settings',data={'action':'resource_profile','resource_profile':'pi3'})
    assert response.status_code==302 and cfg['resource_profile']=='pi3'
    assert cfg['displays']==before and cfg['gui']['background_blur_radius']==7
    for display in cfg['displays'].values():
        effective=presentation.runtime_display_settings(cfg,display)
        assert effective['resource_profile']=='pi3'
        assert '--vd-lavc-threads=2' in presentation.player_presentation_flags(effective)
        assert 'resource_profile' not in display
    assert len(calls)==1


def test_profile_restart_failure_preserves_save(settings_client,monkeypatch):
    client,cfg,saves=settings_client
    def fail(*a,**kw):raise subprocess.TimeoutExpired('systemctl',100)
    monkeypatch.setattr(routes.subprocess,'run',fail)
    response=client.post('/settings',data={'action':'resource_profile','resource_profile':'pi3'},follow_redirects=True)
    assert response.status_code==200 and b'restart the viewer' in response.data
    assert saves[-1]['resource_profile']=='pi3'


def test_invalid_profile_not_saved(settings_client):
    client,cfg,saves=settings_client
    assert client.post('/settings',data={'action':'resource_profile','resource_profile':'unknown'}).status_code==400
    assert not saves


@pytest.mark.parametrize('existing,expected',[(None,'pi3'),('standard','standard'),('pi3','pi3')])
def test_legacy_profile_migration_is_global_and_idempotent(existing,expected):
    cfg={'displays':{'HDMI-1':{'resource_profile':'standard'},'Composite-1':{'resource_profile':'pi3','safe_area':{'left':5}}}}
    if existing is not None:cfg['resource_profile']=existing
    assert utils.upgrade_config(cfg)
    assert cfg['resource_profile']==expected
    assert all('resource_profile' not in d for d in cfg['displays'].values())
    assert cfg['displays']['Composite-1']['safe_area']=={'left':5}
    assert not utils.upgrade_config(cfg)


@pytest.mark.parametrize('endpoint',['/update_app','/full_update'])
def test_updates_use_saved_branch(settings_client,monkeypatch,endpoint):
    client,cfg,saves=settings_client
    cfg['update_branch']='dev';calls=[]
    monkeypatch.setattr(updates,'update',lambda *a,**kw:calls.append((a,kw)))
    assert client.post(endpoint).status_code==202
    assert calls[0][0][1]=='dev'
    assert calls[0][1]['reboot']==(endpoint=='/full_update')


def test_branch_falls_back_to_environment_until_saved():
    assert branches.selected_branch({},'dev')=='dev'
    assert branches.selected_branch({'update_branch':'main'},'dev')=='main'


def test_remote_branches_are_bounded_cached_and_preserve_saved_choice(monkeypatch,tmp_path):
    branches._cache.clear();calls=[]
    def run(args,**kw):
        calls.append((args,kw))
        return SimpleNamespace(stdout='a'*40+'\trefs/heads/feature/display\n'+'b'*40+'\trefs/heads/dev\n')
    monkeypatch.setattr(branches.subprocess,'run',run)
    result=branches.branch_options(tmp_path,'removed-branch',remote=True)
    assert result['branches']==['dev','feature/display','main','removed-branch']
    assert calls[0][0]==['git','ls-remote','--heads','origin']
    assert calls[0][1]['timeout']==8
    assert calls[0][1]['env']['GIT_TERMINAL_PROMPT']=='0'
    branches.branch_options(tmp_path,'dev',remote=True)
    assert len(calls)==1


def test_offline_branches_keep_choices_and_settings_page_never_contacts_remote(monkeypatch,tmp_path):
    branches._cache.clear();calls=[]
    def run(args,**kw):
        calls.append(args)
        if 'ls-remote' in args:raise subprocess.TimeoutExpired(args,8)
        return SimpleNamespace(stdout='refs/remotes/origin/release/test\nrefs/remotes/origin/HEAD\n')
    monkeypatch.setattr(branches.subprocess,'run',run)
    assert 'release/test' in branches.branch_options(tmp_path,'dev')['branches']
    assert all('ls-remote' not in args for args in calls)
    result=branches.branch_options(tmp_path,'custom',remote=True)
    assert not result['available'] and 'custom' in result['branches']


def test_branch_endpoint_returns_offline_choices(settings_client):
    client,cfg,saves=settings_client
    cfg['update_branch']='dev'
    response=client.get('/update_branches')
    assert response.status_code==200
    assert response.json['selected']=='dev'
    assert response.json['available'] is False


def test_global_profile_overrides_stale_per_display_policy():
    display={'resource_profile':'pi3','youtube_quality':'hd1080'}
    effective=presentation.runtime_display_settings({'resource_profile':'standard'},display)
    assert effective['resource_profile']=='standard'
    assert display['resource_profile']=='pi3'
    assert '--vd-lavc-threads=2' not in presentation.player_presentation_flags(effective)


def test_saving_theme_preserves_gui_and_device_settings(settings_client):
    client,cfg,saves=settings_client
    cfg['update_branch']='dev'
    assert client.post('/settings',data={'theme':'light'}).status_code==302
    assert saves[-1]['gui']['background_blur_radius']==7
    assert saves[-1]['resource_profile']=='standard'
    assert saves[-1]['update_branch']=='dev'
