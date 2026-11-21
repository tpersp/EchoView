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
    def run(args, cwd=None, timeout=60, log_path=None):
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
    assert ['git','fetch','origin','+refs/heads/dev:refs/remotes/origin/dev'] in calls
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


def test_run_preserves_private_installer_output_on_failure(tmp_path):
    import sys

    log = tmp_path / 'installer.log'
    with pytest.raises(subprocess.CalledProcessError) as error:
        updates.run([sys.executable, '-c',
                     'import sys; print("installer detail"); '
                     'print("failure detail", file=sys.stderr); sys.exit(1)'],
                    log_path=log)
    assert 'installer detail' in log.read_text()
    assert 'failure detail' in log.read_text()
    assert log.stat().st_mode & 0o777 == 0o600
    assert error.value.stdout is None and error.value.stderr is None


def test_installer_failure_reports_private_log_location(installation, monkeypatch):
    repo, config, token, calls, normal = installation
    def fail(args, **kwargs):
        if 'setup.sh' in args:
            assert kwargs['log_path'].parent.parent == repo / '.update-backups'
            raise subprocess.CalledProcessError(1, args, stderr='private output')
        return normal(args, **kwargs)
    monkeypatch.setattr(updates, 'run', fail)
    with pytest.raises(updates.UpdateError, match='Installer output: .*installer.log') as error:
        updates.update(repo, 'dev', config, token)
    assert 'private output' not in str(error.value)


def test_restart_defers_controller_shutdown_until_after_response(monkeypatch):
    calls = []
    monkeypatch.setattr(updates, 'run', lambda args, **kw: calls.append(args))
    updates.restart_services()
    assert calls[:2] == [
        ['sudo', '-n', 'systemctl', 'restart', 'echoview.service'],
        ['sudo', '-n', 'systemctl', 'is-active', '--quiet', 'echoview.service'],
    ]
    assert calls[-1] == [
        'sudo', '-n', 'systemd-run', '--on-active=5s',
        '--timer-property=AccuracySec=1s', '--collect',
        '/usr/bin/systemctl', 'restart', 'controller.service',
    ]


def test_failed_restart_schedule_never_reports_success(monkeypatch):
    def run(args, **kwargs):
        if 'systemd-run' in args:
            raise subprocess.CalledProcessError(1, args)
    monkeypatch.setattr(updates, 'run', run)
    with pytest.raises(updates.UpdateError, match='Service restart failed'):
        updates.restart_services()


@pytest.mark.parametrize('endpoint',['/update_app','/full_update','/restart_services'])
def test_routes_report_failure_and_pending_truthfully(monkeypatch,endpoint):
    app=Flask(__name__,template_folder=str(Path(routes.__file__).parent/'templates'))
    app.register_blueprint(routes.main_bp)
    monkeypatch.setattr(routes,'log_message',lambda msg:None)
    monkeypatch.setattr(routes,'load_config',lambda:{})
    def fail(*args,**kwargs): raise updates.UpdateError('Installer failed.')
    name='restart_services' if endpoint=='/restart_services' else 'update'
    monkeypatch.setattr(updates,name,fail)
    response=app.test_client().post(endpoint)
    assert response.status_code==500
    assert b'Installer failed.' in response.data
    assert b'setTimeout(reconnect' not in response.data
    monkeypatch.setattr(updates,name,lambda *a,**kw:'backup')
    pending = app.test_client().post(endpoint)
    assert pending.status_code==202
    assert b'setTimeout(reconnect, 10000)' in pending.data
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


def test_low_storage_refuses_update_before_fetch_or_backup(installation, monkeypatch):
    repo, config, token, calls, _ = installation
    monkeypatch.setattr(updates.shutil, 'disk_usage', lambda path: SimpleNamespace(free=100))
    with pytest.raises(updates.UpdateError, match='512 MiB'):
        updates.update(repo, 'main', config, token)
    assert not calls
    assert not (repo / '.update-backups').exists()


@pytest.mark.parametrize('failure', ['missing-checker', 'system-python', 'viewer-python'])
def test_incompatible_release_never_replaces_code_or_restarts(installation, monkeypatch, failure):
    import sys

    repo, config, token, calls, normal = installation
    def fail(args, **kwargs):
        is_checker = args[:2] == ['git', 'show']
        rejected_python = 'python3' if failure == 'system-python' else sys.executable
        if ((failure == 'missing-checker' and is_checker)
                or (failure != 'missing-checker' and args[0] == rejected_python)):
            calls.append(args)
            raise subprocess.CalledProcessError(1, args, stderr='private output')
        return normal(args, **kwargs)
    monkeypatch.setattr(updates, 'run', fail)
    with pytest.raises(updates.UpdateError, match='Installed code and dependencies were not changed'):
        updates.update(repo, 'dev', config, token)
    assert not any('reset' in call or 'setup.sh' in call or 'systemctl' in call
                   or 'systemd-run' in call for call in calls)


def test_preflight_runs_incoming_checker_before_reset(installation, monkeypatch):
    import sys

    repo, config, token, calls, normal = installation
    incoming = '# incoming release compatibility rules\n'
    def run(args, **kwargs):
        result = normal(args, **kwargs)
        if args[:2] == ['git', 'show']:
            return SimpleNamespace(stdout=incoming)
        if '--installer' in args:
            assert Path(args[1]).read_text() == incoming
            assert Path(args[1]).stat().st_mode & 0o777 == 0o600
            assert not any('reset' in call for call in calls)
        return result
    monkeypatch.setattr(updates, 'run', run)
    updates.update(repo, 'dev', config, token)
    assert ['git', 'show', f'{"a" * 40}:echoview/runtime_check.py'] in calls
    assert {call[0] for call in calls if '--installer' in call} == {'python3', sys.executable}


def test_preflight_rejection_with_real_git_and_python(tmp_path, monkeypatch):
    repo = tmp_path / 'repo'
    repo.mkdir()
    def git(*args):
        return subprocess.run(['git', *args], cwd=repo, check=True,
                              capture_output=True, text=True)
    git('init', '-b', 'main')
    (repo / '.gitignore').write_text('.env\n.update*\n')
    (repo / 'echoview').mkdir()
    (repo / 'echoview/runtime_check.py').write_text('raise SystemExit(1)\n')
    git('add', '.')
    git('-c', 'user.name=Test', '-c', 'user.email=test@example.com',
        'commit', '-m', 'Fixture release')
    previous = git('rev-parse', 'HEAD').stdout
    git('remote', 'add', 'origin', str(repo))
    (repo / '.env').write_text('VIEWER_HOME=/custom\n')
    original_run = updates.run
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        assert args[0] != 'sudo'
        return original_run(args, **kwargs)
    monkeypatch.setattr(updates, 'run', run)
    with pytest.raises(updates.UpdateError, match='Release compatibility check failed'):
        updates.update(repo, 'main', repo / 'viewerconfig.json', repo / 'token')
    assert git('rev-parse', 'HEAD').stdout == previous
    assert not any('reset' in call for call in calls)
    logs = list((repo / '.update-backups').glob('before-*/preflight-*.log'))
    assert logs and all(log.stat().st_mode & 0o777 == 0o600 for log in logs)
