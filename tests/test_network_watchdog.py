import os
from pathlib import Path
import subprocess
import pytest

ROOT=Path(__file__).parents[1]


def run_watchdog(tmp_path, primary_results, fallback_results, fallback='gateway'):
    functions=tmp_path/'watchdog.sh'
    functions.write_text((ROOT/'network-watchdog.sh').read_text().rsplit('main "$@"',1)[0])
    harness=r'''
source "$1"
ensure_log_file() { :; }
log() { echo "LOG $1"; }
reboot_system() { echo REBOOT; }
run_recovery() { :; }
a=0; b=0
read -ra primary_results <<< "$PRIMARY_RESULTS"
read -ra fallback_results <<< "$FALLBACK_RESULTS"
fake_ping() {
  local target="${!#}" result
  echo "PING $target"
  if [[ "$target" == nas ]]; then result="${primary_results[$a]:-1}"; a=$((a+1));
  else result="${fallback_results[$b]:-1}"; b=$((b+1)); fi
  return "$result"
}
PING_BIN=fake_ping
main
'''
    # The ping output is intentionally redirected by the real script; counts go to a file.
    harness=harness.replace('echo "PING $target"','echo "PING $target" >> "$CALLS"')
    calls=tmp_path/'calls'
    env=dict(os.environ,WATCHDOG_CONF=str(tmp_path/'absent'),WATCHDOG_TARGET='nas',
             WATCHDOG_FALLBACK_TARGET=fallback,WATCHDOG_ATTEMPTS='5',WATCHDOG_FAIL_THRESHOLD='3',
             PRIMARY_RESULTS=primary_results,FALLBACK_RESULTS=fallback_results,CALLS=str(calls))
    result=subprocess.run(['bash','-c',harness,'test',str(functions)],env=env,capture_output=True,text=True,check=True)
    return result.stdout,calls.read_text().splitlines() if calls.exists() else []


def test_primary_success_never_pings_fallback(tmp_path):
    output,calls=run_watchdog(tmp_path,'0 0 0 0 0','1')
    assert calls==['PING nas']*5 and 'REBOOT' not in output


def test_fallback_success_prevents_reboot(tmp_path):
    output,calls=run_watchdog(tmp_path,'1 1 1 1 1','0 0 0 0 0')
    assert calls==['PING nas','PING gateway']*5 and 'REBOOT' not in output
    assert 'fallback gateway reachable' in output


def test_both_targets_must_fail_for_threshold(tmp_path):
    output,calls=run_watchdog(tmp_path,'1 1 1 1 1','1 1 1 1 1')
    assert calls==['PING nas','PING gateway']*3 and output.count('REBOOT')==1


def test_either_target_recovery_resets_consecutive_failures(tmp_path):
    output,calls=run_watchdog(tmp_path,'1 1 0 1 1','1 0 1 1')
    assert len(calls)==9 and 'REBOOT' not in output


def test_old_single_target_behavior_is_preserved(tmp_path):
    output,calls=run_watchdog(tmp_path,'1 1 1','0',fallback='')
    assert calls==['PING nas']*3 and output.count('REBOOT')==1


def test_invalid_fallback_does_not_trigger_reboot(tmp_path):
    output,calls=run_watchdog(tmp_path,'1','1',fallback='-bad')
    assert not calls and 'REBOOT' not in output and 'ERROR invalid' in output


@pytest.mark.parametrize('enabled',[True,False])
def test_installer_refresh_preserves_both_targets_and_respects_enablement(tmp_path,enabled):
    source=(ROOT/'setup.sh').read_text()
    start=source.index('  if systemctl is-enabled --quiet network-watchdog.timer; then')
    end=source.index('\nfi\n\n#',start)
    branch=source[start:end]
    conf=tmp_path/'network-watchdog.conf'
    conf.write_text('WATCHDOG_TARGET=nas\nWATCHDOG_FALLBACK_TARGET=gateway\nWATCHDOG_ATTEMPTS=7\nWATCHDOG_FAIL_THRESHOLD=4\n')
    harness='\nVIEWER_HOME="$1"\nWATCHDOG_CONF_FILE="$VIEWER_HOME/network-watchdog.conf"\nsystemctl() { return "$ENABLED_STATUS"; }\ndetect_watchdog_default_target() { echo default-gateway; }\ninstall_network_watchdog() { printf \'%s\\n\' "$@" > "$VIEWER_HOME/installed"; }\n'+branch
    env=dict(os.environ,ENABLED_STATUS='0' if enabled else '1')
    subprocess.run(['bash','-c',harness,'test',str(tmp_path)],env=env,check=True,capture_output=True,text=True)
    if enabled:assert (tmp_path/'installed').read_text().splitlines()==['nas','7','4','gateway']
    else:assert not (tmp_path/'installed').exists()


@pytest.mark.parametrize('fallback',['gateway',''])
def test_install_writes_both_target_fields_without_real_service_actions(tmp_path,fallback):
    source=(ROOT/'setup.sh').read_text()
    start=source.index('install_network_watchdog() {')
    end=source.index('\ncleanup_legacy_watchdog_cron\n',start)
    function=source[start:end].replace('/etc/systemd/system/',str(tmp_path/'units')+'/')
    (tmp_path/'units').mkdir()
    harness=r'''
set -e
VIEWER_HOME="$1/app"
VIEWER_USER=fixture
SCRIPT_DIR="$2"
mkdir -p "$VIEWER_HOME"
id() { echo 1000; }
chown() { :; }
systemctl() { :; }
'''+function+'\ninstall_network_watchdog nas 5 3 "$3"\n'
    subprocess.run(['bash','-c',harness,'test',str(tmp_path),str(ROOT),fallback],check=True,capture_output=True,text=True)
    conf=(tmp_path/'app/network-watchdog.conf').read_text()
    assert 'WATCHDOG_TARGET=nas\n' in conf
    assert f'WATCHDOG_FALLBACK_TARGET={fallback}\n' in conf
    assert (tmp_path/'app/bin/network-watchdog.sh').read_text()==(ROOT/'network-watchdog.sh').read_text()


def test_recovery_entrypoint_forwards_user_and_log_and_reports_failure(tmp_path):
    import sys,json
    app=tmp_path/'app';(app/'bin').mkdir(parents=True);(app/'echoview').mkdir()
    functions=app/'bin/watchdog.sh'
    functions.write_text((ROOT/'network-watchdog.sh').read_text().rsplit('main "$@"',1)[0])
    (app/'echoview/watchdog_recovery.py').write_text('import os,json,sys;print(json.dumps([os.getenv("WATCHDOG_USER"),os.getenv("WATCHDOG_LOG"),sys.argv[1]]));sys.exit(1)')
    harness='source "$1"; target=nas; fallback=gateway; WATCHDOG_USER=fixture; WATCHDOG_LOG=/local/test.log; log() { echo ERROR; }; run_recovery storage'
    env=dict(os.environ,WATCHDOG_CONF=str(tmp_path/'absent'),WATCHDOG_PYTHON=sys.executable)
    result=subprocess.run(['bash','-c',harness,'test',str(functions)],env=env,capture_output=True,text=True)
    assert result.returncode==1
    assert json.loads(result.stdout.splitlines()[0])==['fixture','/local/test.log','storage']
