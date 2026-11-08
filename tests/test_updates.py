import os
from pathlib import Path
from types import SimpleNamespace
import subprocess

import pytest
from flask import Flask
from echoview import updates
from echoview.web import routes


@pytest.fixture
def installation(tmp_path, monkeypatch):
    repo = tmp_path / 'repo'
    repo.mkdir()
    env = repo / '.env'; env.write_text('VIEWER_HOME=/custom\nIMAGE_DIR=/media\n')
    config = repo / 'viewerconfig.json'; config.write_text('{"aspect":"4:3","safe_area":5}')
    token = tmp_path / 'private-token'; token.write_text('secret-refresh-token')
    calls = []
    def run(args, cwd=None, timeout=60):
        calls.append(args)
        value = ''
        if args[:3] == ['git','rev-parse','--verify']: value = 'a'*40
        elif args == ['git','rev-parse','HEAD']: value = 'b'*40
        return SimpleNamespace(stdout=value)
    monkeypatch.setattr(updates, 'run', run)
    return repo,config,token,calls,run


@pytest.mark.parametrize('reboot',[False,True])
def test_update_always_installs_and_preserves_settings(installation,reboot):
    repo,config,token,calls,_ = installation
    original = [p.read_bytes() for p in (repo/'.env',config,token)]
    name = updates.update(repo,'dev',config,token,reboot)
    assert ['sudo','-n','bash','setup.sh','--auto-update'] in calls
    assert [p.read_bytes() for p in (repo/'.env',config,token)] == original
    backup = repo/'.update-backups'/name
    assert (backup/'2-private-token').read_text() == 'secret-refresh-token'
    assert (backup.stat().st_mode & 0o777) == 0o700
    assert ((backup/'2-private-token').stat().st_mode & 0o777) == 0o600
    assert ('reboot' in calls[-1]) is reboot
    assert all('checkout' not in call for call in calls)


@pytest.mark.parametrize('stage', ['fetch','reset','setup.sh','restart','reboot'])
def test_failed_stage_never_proceeds_to_later_action(installation,monkeypatch,stage):
    repo,config,token,calls,normal = installation
    def fail(args,**kwargs):
        if stage in args:
            calls.append(args)
            raise subprocess.CalledProcessError(1,args,stderr='private output')
        return normal(args,**kwargs)
    monkeypatch.setattr(updates,'run',fail)
    with pytest.raises(updates.UpdateError) as error:
        updates.update(repo,'dev',config,token,reboot=stage=='reboot')
    assert 'private output' not in str(error.value)
    assert stage in calls[-1]


def test_dirty_checkout_not_reset(installation,monkeypatch):
    repo,config,token,calls,normal=installation
    def dirty(args,**kwargs):
        if 'status' in args: return SimpleNamespace(stdout=' M viewer.py')
        return normal(args,**kwargs)
    monkeypatch.setattr(updates,'run',dirty)
    with pytest.raises(updates.UpdateError,match='Local tracked changes'):
        updates.update(repo,'dev',config,token)
    assert not any('reset' in x for x in calls)


def test_concurrent_update_rejected(installation):
    import fcntl
    repo,config,token,calls,_=installation
    with (repo/'.update.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(updates.UpdateError,match='already running'):
            updates.update(repo,'dev',config,token)
    assert not calls


@pytest.mark.parametrize('endpoint',['/update_app','/full_update','/restart_services'])
def test_routes_report_failure_and_pending_truthfully(monkeypatch,endpoint):
    app=Flask(__name__,template_folder=str(Path(routes.__file__).parent/'templates'))
    app.register_blueprint(routes.main_bp)
    monkeypatch.setattr(routes,'log_message',lambda msg:None)
    def fail(*args,**kwargs): raise updates.UpdateError('Installer failed.')
    name='restart_services' if endpoint=='/restart_services' else 'update'
    monkeypatch.setattr(updates,name,fail)
    response=app.test_client().post(endpoint)
    assert response.status_code==500
    assert b'Installer failed.' in response.data
    monkeypatch.setattr(updates,name,lambda *a,**kw:'backup')
    assert app.test_client().post(endpoint).status_code==202
    if endpoint=='/restart_services': assert app.test_client().get(endpoint).status_code==405


def test_display_readiness_checks_and_timeout(tmp_path):
    script=Path(__file__).resolve().parents[1]/'scripts/wait-for-display.sh'
    tool=tmp_path/'xrandr';tool.write_text('#!/bin/sh\nexit "${TASK_X_STATUS:-0}"\n');tool.chmod(0o755)
    env={**os.environ,'PATH':str(tmp_path)+os.pathsep+os.environ['PATH'],'ECHOVIEW_DISPLAY_WAIT_SECONDS':'1'}
    assert subprocess.run(['bash',str(script)],env=env,capture_output=True,timeout=5).returncode==0
    result=subprocess.run(['bash',str(script)],env={**env,'TASK_X_STATUS':'1'},capture_output=True,timeout=5)
    assert result.returncode==1
    assert b'X display did not become ready' in result.stderr


def test_target_tracking_configuration_is_refused(installation,monkeypatch):
    repo,config,token,calls,normal=installation
    def tracked(args,**kwargs):
        if 'ls-tree' in args: return SimpleNamespace(stdout='.env')
        return normal(args,**kwargs)
    monkeypatch.setattr(updates,'run',tracked)
    with pytest.raises(updates.UpdateError,match='Target revision tracks'):
        updates.update(repo,'dev',config,token)
    assert not any('reset' in x for x in calls)


def test_missing_environment_is_not_recreated(installation):
    repo,config,token,calls,_=installation
    (repo/'.env').unlink()
    with pytest.raises(updates.UpdateError,match='Existing .env is missing'):
        updates.update(repo,'dev',config,token)
    assert not (repo/'.env').exists()
    assert not calls
