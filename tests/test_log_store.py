from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import subprocess
import sys

from echoview.log_store import append_log


def writer(args):
    path,index=args
    for number in range(80):
        assert append_log(path,f'writer={index} entry={number} '+('x'*80),max_bytes=1024)


def test_rotation_bounds_and_archive_order(tmp_path):
    path=tmp_path/'viewer.log'
    for number in range(40):assert append_log(path,f'entry={number} '+('x'*80),max_bytes=256)
    logs=[path]+[Path(f'{path}.{i}') for i in range(1,4)]
    assert all(file.exists() and file.stat().st_size<=256 for file in logs)
    assert b'entry=39 ' in path.read_bytes()
    assert b'entry=0 ' not in b''.join(file.read_bytes() for file in logs)
    assert sorted(p.name for p in tmp_path.iterdir())==['viewer.log','viewer.log.1','viewer.log.2','viewer.log.3','viewer.log.lock']


def test_migration_of_oversized_active_and_archives_and_huge_entry(tmp_path):
    path=tmp_path/'viewer.log'
    path.write_bytes(b'old'*1000)
    for index in range(1,4):Path(f'{path}.{index}').write_bytes(b'archive'*1000)
    assert append_log(path,'a'*10000,max_bytes=512)
    assert all(file.stat().st_size<=512 for file in tmp_path.iterdir())
    assert path.read_bytes().endswith(b'\n')


def test_concurrent_processes_use_stable_lock_across_rotations(tmp_path):
    path=tmp_path/'viewer.log'
    with ProcessPoolExecutor(max_workers=4) as pool:
        list(pool.map(writer,[(str(path),index) for index in range(4)]))
    for file in [path]+[Path(f'{path}.{i}') for i in range(1,4)]:
        assert file.stat().st_size<=1024
        for line in file.read_text().splitlines():assert 'writer=' in line and 'entry=' in line


def test_cli_watchdog_writer_uses_same_limits_and_never_executes_input(tmp_path):
    path=tmp_path/'viewer.log'
    code=Path(__file__).parents[1]/'echoview/log_store.py'
    result=subprocess.run([sys.executable,str(code),str(path)],input='$(not-a-command)\nprivate-data',text=True)
    assert result.returncode==0
    assert '$(not-a-command)' in path.read_text()


def test_write_failure_does_not_raise(tmp_path):
    blocker=tmp_path/'file';blocker.write_text('not a directory')
    assert append_log(blocker/'viewer.log','message') is False


def test_installed_watchdog_uses_bounded_writer_with_custom_log_location(tmp_path):
    import os
    import shutil
    root=Path(__file__).parents[1]
    app=tmp_path/'app';(app/'bin').mkdir(parents=True);(app/'.venv/bin').mkdir(parents=True);(app/'echoview').mkdir()
    (app/'.venv/bin/python3').symlink_to(sys.executable)
    shutil.copy(root/'echoview/log_store.py',app/'echoview/log_store.py')
    source=(root/'network-watchdog.sh').read_text()
    assert source.rstrip().endswith('main "$@"')
    functions=app/'bin/watchdog.sh';functions.write_text(source.rsplit('main "$@"',1)[0])
    path=tmp_path/'custom-logs/viewer.log';path.parent.mkdir();path.write_bytes(b'x'*(6*1024*1024))
    env=dict(os.environ,WATCHDOG_LOG=str(path),WATCHDOG_CONF=str(tmp_path/'absent.conf'))
    subprocess.run(['bash','-c','source "$1"; log "bounded shell report"','check',str(functions)],env=env,check=True)
    assert 'bounded shell report' in path.read_text()
    assert all(item.stat().st_size<=5*1024*1024 for item in path.parent.iterdir())


def test_watchdog_writer_failure_never_reverts_to_unbounded_append(tmp_path):
    import os
    source=(Path(__file__).parents[1]/'network-watchdog.sh').read_text().rsplit('main "$@"',1)[0]
    functions=tmp_path/'watchdog.sh';functions.write_text(source)
    path=tmp_path/'viewer.log';path.write_text('unchanged')
    env=dict(os.environ,WATCHDOG_LOG=str(path),WATCHDOG_CONF=str(tmp_path/'absent.conf'),WATCHDOG_PYTHON='/nonexistent-python')
    result=subprocess.run(['bash','-c','source "$1"; log "report"','check',str(functions)],env=env,capture_output=True,text=True)
    assert result.returncode==0
    assert path.read_text()=='unchanged'
    assert 'Network watchdog: report' in result.stderr
