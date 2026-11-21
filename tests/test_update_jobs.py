import json
from pathlib import Path
import subprocess
import threading
from types import SimpleNamespace

import pytest
from flask import Flask

from echoview import update_jobs as jobs, updates
from echoview.web import routes


@pytest.fixture
def pending_worker(monkeypatch):
    workers = []
    class Thread:
        def __init__(self, target, **kwargs):
            self.target = target
            workers.append(self)
        def start(self):
            pass
    monkeypatch.setattr(jobs.threading, 'Thread', Thread)
    yield workers
    # Always release the lock, including if an assertion fails.
    for worker in workers:
        if worker.target is not None:
            worker.target()
            worker.target = None


def finish(workers):
    target = workers[-1].target
    workers[-1].target = None
    target()


def test_progress_persists_and_duplicate_start_is_refused(tmp_path, monkeypatch, pending_worker):
    def install(*args, progress, **kwargs):
        progress('Installing dependencies')
        assert jobs.status(tmp_path)['message'] == 'Installing dependencies'
        return 'before-example'
    monkeypatch.setattr(updates, 'update', install)
    state = jobs.start(tmp_path, 'main', 'config', 'token')
    assert jobs.status(tmp_path)['id'] == state['id']
    assert (tmp_path / '.update-state.json').stat().st_mode & 0o777 == 0o600
    with pytest.raises(updates.UpdateError, match='already running'):
        jobs.start(tmp_path, 'main', 'config', 'token')
    finish(pending_worker)
    assert jobs.status(tmp_path)['status'] == 'awaiting_restart'
    with pytest.raises(updates.UpdateError, match='wait for the controller'):
        jobs.start(tmp_path, 'main', 'config', 'token')
    monkeypatch.setattr(jobs, 'INSTANCE', 'new-controller')
    state = jobs.status(tmp_path)
    assert state['status'] == 'completed'
    assert state['backup'] == 'before-example'


@pytest.mark.parametrize('error, expected', [
    (updates.UpdateError('Installer failed'), 'Installer failed'),
    (RuntimeError('secret command output'), 'An unexpected update error occurred'),
])
def test_worker_failure_is_persisted_and_allows_retry(tmp_path, monkeypatch, pending_worker, error, expected):
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(updates, 'update', fail)
    jobs.start(tmp_path, 'main', 'config', 'token')
    finish(pending_worker)
    state = jobs.status(tmp_path)
    assert state['status'] == 'failed'
    assert expected in state['message']
    assert 'secret' not in json.dumps(state)
    jobs.start(tmp_path, 'main', 'config', 'token')


def test_abandoned_worker_becomes_interrupted_without_automatic_retry(tmp_path):
    jobs._write(tmp_path, {'status': 'running', 'id': 'old-job'})
    assert jobs.status(tmp_path)['status'] == 'interrupted'
    assert jobs.status(tmp_path)['id'] == 'old-job'
    assert json.loads((tmp_path / '.update-state.json').read_text())['status'] == 'interrupted'


def test_real_background_worker_returns_without_waiting_for_install(tmp_path, monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    workers = []
    original_thread = threading.Thread
    def track_thread(**kwargs):
        thread = original_thread(**kwargs)
        workers.append(thread)
        return thread
    def install(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return 'before-example'
    monkeypatch.setattr(updates, 'update', install)
    monkeypatch.setattr(jobs.threading, 'Thread', track_thread)
    try:
        jobs.start(tmp_path, 'main', 'config', 'token')
        assert entered.wait(2)
        assert jobs.status(tmp_path)['status'] == 'running'
        with pytest.raises(updates.UpdateError, match='already running'):
            jobs.start(tmp_path, 'main', 'config', 'token')
    finally:
        release.set()
        for thread in workers:
            thread.join(3)
    assert jobs.status(tmp_path)['status'] == 'awaiting_restart'


@pytest.mark.parametrize('available', [True, False])
def test_release_check_reports_revision_version_and_changes_without_installing(tmp_path, monkeypatch, available):
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        value = ''
        if args[:3] == ['git', 'rev-parse', '--verify']:
            value = 'a' * 40
        elif args == ['git', 'rev-parse', 'HEAD']:
            value = ('b' if available else 'a') * 40
        elif args[:2] == ['git', 'show']:
            value = 'APP_VERSION = "1.20.0"\r\n'
        elif args[:2] == ['git', 'log']:
            value = 'Improve update experience\nPreserve settings\n'
        return SimpleNamespace(stdout=value)
    monkeypatch.setattr(updates, 'run', run)
    result = jobs.check_release(tmp_path, 'main')
    assert result['available'] is available
    assert result['version'] == '1.20.0'
    assert result['changes'][0] == 'Improve update experience'
    assert not any('reset' in call or 'sudo' in call for call in calls)


def test_release_check_does_not_expose_command_errors(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, 'git', stderr='private remote details')
    monkeypatch.setattr(updates, 'run', fail)
    with pytest.raises(updates.UpdateError, match='Could not check') as error:
        jobs.check_release(tmp_path, 'main')
    assert 'private' not in str(error.value)


def test_json_update_routes_start_quickly_and_status_is_uncached(tmp_path, monkeypatch, pending_worker):
    app = Flask(__name__)
    app.register_blueprint(routes.main_bp)
    monkeypatch.setattr(routes, 'VIEWER_HOME', tmp_path)
    monkeypatch.setattr(routes, 'load_config', lambda: {'update_branch': 'main'})
    monkeypatch.setattr(routes, 'log_message', lambda message: None)
    monkeypatch.setattr(updates, 'update', lambda *args, **kwargs: 'before-example')
    client = app.test_client()
    response = client.post('/update_app', headers={'Accept': 'application/json'})
    assert response.status_code == 202
    assert response.json['branch'] == 'main'
    assert client.post('/full_update', headers={'Accept': 'application/json'}).status_code == 409
    response = client.get('/update_status')
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.json['status'] == 'running'
    assert response.json['version'] == routes.APP_VERSION
    finish(pending_worker)
    assert client.get('/update_status').json['status'] == 'awaiting_restart'
    assert client.get('/check_update').status_code == 405
    monkeypatch.setattr(jobs, 'check_release', lambda repo, branch: {'branch': branch})
    assert client.post('/check_update').json['branch'] == 'main'


@pytest.mark.parametrize('branch', ['--upload-pack=bad', 'main~1', '../main'])
def test_invalid_branch_never_starts_worker_or_fetches(tmp_path, branch):
    with pytest.raises(updates.UpdateError):
        jobs.start(tmp_path, branch, 'config', 'token')
    with pytest.raises(updates.UpdateError):
        jobs.check_release(tmp_path, branch)
    assert not list(tmp_path.iterdir())
