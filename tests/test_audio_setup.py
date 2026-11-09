"""Exercise installer audio stages without apt, users, systemd or device writes."""
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'scripts/setup-runtime.sh'


@pytest.fixture
def audio_fixture(tmp_path):
    home = tmp_path / 'viewer-home'
    home.mkdir()
    tools = tmp_path / 'tools'
    tools.mkdir()
    for name in ('systemctl', 'apt-get'):
        tool = tools / name
        tool.write_text('''#!/bin/bash
printf '%s %s\\n' "${0##*/}" "$*" >> "$TASK_AUDIO_LOG"
if [[ "$*" == 'start user@1007.service' && "${TASK_AUDIO_MANAGER_READY:-1}" == 1 ]]; then touch "$TASK_AUDIO_MARKER"; fi
if [[ -n "${TASK_AUDIO_FAIL:-}" && "$*" == *"$TASK_AUDIO_FAIL"* ]]; then exit 42; fi
''')
        tool.chmod(0o755)
    env = {**os.environ, 'PATH': str(tools)+os.pathsep+os.environ['PATH'],
           'TASK_AUDIO_LOG': str(tmp_path/'commands'), 'TASK_AUDIO_HOME': str(home), 'TASK_AUDIO_MARKER': str(tmp_path/'bus-ready')}
    return home, env


def audio_call(fixture, action, **options):
    home, env = fixture
    command = '''source "$1"
dpkg-query() { printf '%s' "${TASK_AUDIO_PULSE:-unknown ok not-installed}"; }
getent() { printf 'viewer:x:1007:1007:Viewer:%s:/bin/bash\\n' "$TASK_AUDIO_HOME"; }
id() { printf 'viewer-group\\n'; }
chown() { printf 'chown %s\\n' "$*" >> "$TASK_AUDIO_LOG"; }
runuser() {
 printf 'runuser %s\\n' "$*" >> "$TASK_AUDIO_LOG"
 shift 3
 "$@"
}
audio_session_ready() { [[ "${TASK_AUDIO_BUS:-0}" == 1 || -f "$TASK_AUDIO_MARKER" ]]; }
sleep() { :; }
if [[ "$2" == install ]]; then install_audio_runtime; else configure_user_audio viewer 1007; fi
'''
    result = subprocess.run(['bash','-c',command,'test',str(HELPER),action],
        env={**env,**options},capture_output=True,text=True,timeout=10)
    log = Path(env['TASK_AUDIO_LOG'])
    return result, log.read_text() if log.exists() else ''


def test_lite_install_adds_complete_audio_stack(audio_fixture):
    result, log = audio_call(audio_fixture,'install')
    assert result.returncode == 0
    assert 'apt-get install -y pipewire pipewire-pulse wireplumber rtkit' in log


def test_existing_pulseaudio_is_not_replaced(audio_fixture):
    result, log = audio_call(audio_fixture,'install',TASK_AUDIO_PULSE='install ok installed')
    assert result.returncode == 0
    assert 'apt-get install -y rtkit' in log
    assert 'pipewire-pulse' not in log


def test_package_failure_is_reported(audio_fixture):
    result, log = audio_call(audio_fixture,'install',TASK_AUDIO_FAIL='install')
    assert result.returncode != 0


def test_fresh_user_starts_user_manager_before_enabling_audio(audio_fixture):
    result, log = audio_call(audio_fixture,'configure')
    assert result.returncode == 0
    assert 'systemctl start user@1007.service' in log
    assert log.index('systemctl start user@1007.service') < log.index('systemctl --user enable')
    assert 'enable pipewire.socket pipewire-pulse.socket wireplumber.service' in log
    assert 'systemctl --user start pipewire.service' in log
    assert 'XDG_RUNTIME_DIR=/run/user/1007' in log
    assert 'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1007/bus' in log
    home, _ = audio_fixture
    config=home/'.config/wireplumber/wireplumber.conf.d/60-echoview-audio.conf'
    assert 'device.routes.default-sink-volume = 1.0' in config.read_text()
    assert '--no-reload' not in log


def test_active_session_starts_and_checks_audio(audio_fixture):
    result, log = audio_call(audio_fixture,'configure',TASK_AUDIO_BUS='1')
    assert result.returncode == 0
    assert 'systemctl --user daemon-reload' in log
    assert 'systemctl --user start pipewire.service pipewire-pulse.service wireplumber.service' in log
    assert 'systemctl --user is-active --quiet pipewire.service pipewire-pulse.service wireplumber.service' in log


def test_audio_start_failure_stops_setup(audio_fixture):
    result, log = audio_call(audio_fixture,'configure',TASK_AUDIO_BUS='1',TASK_AUDIO_FAIL='start')
    assert result.returncode != 0
    assert 'is-active --quiet' not in log


def test_upgrade_preserves_route_volume_and_custom_configuration(audio_fixture):
    home, _ = audio_fixture
    state=home/'.local/state/wireplumber/default-routes'
    state.parent.mkdir(parents=True)
    state.write_text('existing output and volume')
    config=home/'.config/wireplumber/wireplumber.conf.d/60-echoview-audio.conf'
    config.parent.mkdir(parents=True)
    config.write_text('wireplumber.settings = { device.routes.default-sink-volume = 0.125 }\n')
    for _ in range(2):
        result, log=audio_call(audio_fixture,'configure',TASK_AUDIO_BUS='1')
        assert result.returncode == 0
    assert state.read_text()=='existing output and volume'
    assert 'default-sink-volume = 0.125' in config.read_text()
    assert 'set-default' not in log and 'set-volume' not in log


def test_pulseaudio_session_only_enables_existing_server(audio_fixture):
    result, log=audio_call(audio_fixture,'configure',TASK_AUDIO_PULSE='install ok installed',TASK_AUDIO_BUS='1')
    assert result.returncode == 0
    assert 'enable pulseaudio.socket' in log and 'start pulseaudio.socket' in log
    assert 'pipewire.service' not in log
    home,_=audio_fixture
    assert not (home/'.config/wireplumber').exists()


def test_generated_viewer_service_has_user_audio_environment(tmp_path):
    script=(ROOT/'setup.sh').read_text()
    start=script.index('cat <<EOF > "$ECHOVIEW_SERVICE"')
    content=script[start:].split('\nEOF',1)[0].split('\n',1)[1]
    env={**os.environ,'USER_ID':'1007','VIEWER_USER':'viewer','VIEWER_HOME':'/custom/app',
         'ENV_FILE':'/custom/app/.env','VENV_DIR':'/custom/app/.venv','SCRIPT_DIR':'/custom/app',
         'XAUTHORITY':'/custom/auth','QTWEBENGINE_FLAGS':'--autoplay-policy=no-user-gesture-required'}
    result=subprocess.run(['bash','-c','cat <<EOF\n'+content+'\nEOF\n'],env=env,text=True,capture_output=True,check=True)
    assert 'XDG_RUNTIME_DIR=/run/user/1007' in result.stdout
    assert 'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1007/bus' in result.stdout


def test_missing_user_bus_is_reported_before_enabling_or_starting_audio(audio_fixture):
    result, log = audio_call(audio_fixture, 'configure', TASK_AUDIO_MANAGER_READY='0')
    assert result.returncode != 0
    assert 'audio bus is unavailable' in result.stderr
    assert 'systemctl --user enable' not in log
