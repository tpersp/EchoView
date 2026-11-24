import json
from pathlib import Path
import subprocess
import time
import pytest
from flask import Flask
from echoview import recovery
from echoview.web import routes


def test_snapshot_is_bounded_allowlisted_and_expires(tmp_path):
    recovery.publish(tmp_path,[dict(name='HDMI-1',mode='spotify',problem=None,uses_media=False,token='secret')])
    state=recovery.read(tmp_path)
    assert state['pid']>0
    assert 'secret' not in (tmp_path/'recovery.json').read_text()
    assert recovery.read(tmp_path,now=state['at']+21) is None
    (tmp_path/'recovery.json').write_bytes(b'x'*65537)
    assert recovery.read(tmp_path) is None
    (tmp_path/'recovery.json').write_text('{bad')
    assert recovery.read(tmp_path) is None


def test_network_mount_detection_does_not_probe_media(monkeypatch):
    monkeypatch.setattr(Path,'exists',lambda *args:pytest.fail('No filesystem probe'))
    fstab='//host/share /mnt/media cifs credentials=/private,defaults 0 0\n'
    assert recovery.storage_missing('/mnt/media/folder',fstab,'')
    mounted='24 21 0:22 / /mnt/media rw - cifs //host/share rw\n'
    assert not recovery.storage_missing('/mnt/media/folder',fstab,mounted)
    assert not recovery.storage_missing('/mnt/media-other',fstab,'')
    assert not recovery.storage_missing('/local/media',fstab,'')
    assert recovery.storage_missing('/mnt/my media/folder','server:/path /mnt/my\\040media nfs defaults 0 0','')


def test_healthy_empty_mount_missing_and_stale_modes():
    cfg={'displays':{'HDMI-1':{'mode':'videos'},'HDMI-2':{'mode':'spotify'}}}
    state={'pid':10,'displays':[dict(name='HDMI-1',mode='videos',problem=None,uses_media=True)]}
    assert recovery.status(cfg,state)['issues']==[]
    result=recovery.status(cfg,state,True)
    assert [issue['code'] for issue in result['issues']]==['storage_missing']
    state['displays'][0].update(problem='media_slow')
    assert len(recovery.status(cfg,state,True)['issues'])==1
    cfg['displays']['HDMI-1']['mode']='calibration'
    assert recovery.status(cfg,state)['issues']==[]
    state['displays'][0].update(mode='calibration',uses_media=False,problem=None)
    assert recovery.status(cfg,state,True)['issues']==[]
    assert recovery.status(cfg,None)['issues'][0]['code']=='viewer_unavailable'


@pytest.mark.parametrize('code',list(recovery.PROBLEMS))
def test_problem_messages_have_known_actions_and_clear_when_state_recovers(code):
    cfg={'displays':{'screen':{'mode':'scheduled'}}}
    state={'pid':12,'displays':[dict(name='screen',mode='videos',problem=code,uses_media=True)]}
    issue=recovery.status(cfg,state)['issues'][0]
    assert issue['code']==code and issue['action'] in ('restart','retry','media','displays','spotify')
    state['displays'][0]['problem']=None
    assert recovery.status(cfg,state)['issues']==[]


def test_invalid_problem_payload_is_not_returned():
    cfg={'displays':{'screen':{'mode':'videos'}}}
    for bad in ({'url':'secret'},'secret-token',[] ): 
        state={'pid':1,'displays':[dict(name='screen',mode='videos',problem=bad)]}
        assert recovery.status(cfg,state)['issues']==[]


@pytest.fixture
def client(monkeypatch,tmp_path):
    app=Flask(__name__,template_folder=str(Path(routes.__file__).parent/'templates'));app.secret_key='fixture';app.register_blueprint(routes.main_bp)
    monkeypatch.setattr(routes,'load_config',lambda:{'displays':{'screen':{'mode':'videos'}}})
    monkeypatch.setattr(routes,'state_directory',lambda home:tmp_path)
    return app.test_client(),tmp_path


def test_status_endpoint_is_local_read_only_and_no_store(client,monkeypatch):
    test,directory=client
    recovery.publish(directory,[dict(name='screen',mode='videos',problem='media_failed',uses_media=True)])
    monkeypatch.setattr(routes,'save_config',lambda *args:pytest.fail('No settings writes'))
    monkeypatch.setattr(routes.subprocess,'run',lambda *args,**kwargs:pytest.fail('No system commands'))
    response=test.get('/recovery_status')
    assert response.status_code==200 and response.headers['Cache-Control']=='no-store'
    assert response.json['issues'][0]['code']=='media_failed'


def test_restart_requires_post_and_is_bounded_sanitized(client,monkeypatch):
    test,_=client
    assert test.get('/restart_viewer').status_code==405
    calls=[]
    def run(command,**kwargs):calls.append((command,kwargs))
    monkeypatch.setattr(routes.subprocess,'run',run)
    response=test.post('/restart_viewer',headers={'Accept':'application/json'})
    assert response.status_code==202
    assert calls[0][0]==['sudo','-n','systemctl','restart','echoview.service']
    assert calls[0][1]['timeout']==15
    def denied(*args,**kwargs):raise subprocess.CalledProcessError(1,args[0],stderr='private credentials')
    monkeypatch.setattr(routes.subprocess,'run',denied)
    response=test.post('/restart_viewer',headers={'Accept':'application/json'})
    assert response.status_code==503 and b'private credentials' not in response.data


def test_standalone_status_page_never_lists_media_or_probes_displays(client,monkeypatch):
    test,_=client
    monkeypatch.setattr(routes,'get_subfolders',lambda:pytest.fail('No NAS listing'))
    monkeypatch.setattr(routes,'detect_monitors_extended',lambda:pytest.fail('No display command'))
    response=test.get('/status')
    assert response.status_code==200
    assert b'data-always-visible="true"' in response.data
    assert b'/recovery_status' in response.data


def test_dead_viewer_is_not_reported_as_fresh(tmp_path,monkeypatch):
    recovery.publish(tmp_path,[])
    def dead(*args):raise ProcessLookupError
    monkeypatch.setattr(recovery.os,'kill',dead)
    assert recovery.read(tmp_path) is None


def test_missing_storage_is_reported_even_while_viewer_cannot_start():
    cfg={'displays':{'screen':{'mode':'videos'}}}
    assert [issue['code'] for issue in recovery.status(cfg,None,True)['issues']]==['storage_missing','viewer_unavailable']
