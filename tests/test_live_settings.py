from copy import deepcopy
import json
import threading
import time

from echoview.live_settings import visual_changes, request_update, VisualSettingsReceiver, atomic_json


def config():
    return {'displays': {'one': {'mode':'spotify','spotify_font_size':18}, 'two':{'mode':'videos'}}}


def test_spotify_time_toggle_is_a_live_visual_change():
    before = config()
    after = deepcopy(before)
    after['displays']['one']['spotify_show_time'] = True
    assert visual_changes(before, after) == ['one']


def test_spotify_background_is_live_and_does_not_change_modes():
    before=config();after=deepcopy(before)
    after['displays']['one'].update(spotify_background_mode='gradient',spotify_background_dim=40)
    assert visual_changes(before,after)==['one']


def test_only_spotify_visual_changes_are_eligible():
    before=config(); after=deepcopy(before)
    after['displays']['one']['spotify_font_size']=24
    assert visual_changes(before,after)==['one']
    after['displays']['two']['video_volume']=20
    assert visual_changes(before,after)==[]
    after=deepcopy(before); after['spotify']={'client_id':'new'}
    assert visual_changes(before,after)==[]
    after=deepcopy(before); after['displays']['one']['mode']='random_image'
    assert visual_changes(before,after)==[]
    after=deepcopy(before); after['displays']['one']['fallback_mode']='none'
    assert visual_changes(before,after)==[]
    assert visual_changes(before,before)==[]


def test_request_acknowledged_once_and_saved_config_not_exposed(tmp_path):
    calls=[]; stop=threading.Event()
    receiver=VisualSettingsReceiver(tmp_path,lambda request:calls.append(request) or True)
    def run():
        while not stop.wait(.01): receiver.poll()
    worker=threading.Thread(target=run); worker.start()
    try:
        cfg=dict(config(),spotify={'client_secret':'private'})
        assert request_update(tmp_path,cfg,['one'],timeout=1)
        receiver.poll()
        assert len(calls)==1
        assert 'private' not in (tmp_path/'visual-request.json').read_text()
        assert (tmp_path/'visual-request.json').stat().st_mode&0o777==0o600
    finally: stop.set(); worker.join()


def test_missing_ack_and_wrong_revision_never_report_success(tmp_path):
    atomic_json(tmp_path,'visual-ack.json',{'revision':'old','applied':True})
    assert not request_update(tmp_path,config(),['one'],timeout=.05)


def test_expired_and_failed_requests_are_acknowledged_as_failed(tmp_path):
    calls=[]
    receiver=VisualSettingsReceiver(tmp_path,lambda r:calls.append(r) or True)
    atomic_json(tmp_path,'visual-request.json',{'revision':'expired','expires':time.time()-1})
    receiver.poll(); assert not calls
    assert json.loads((tmp_path/'visual-ack.json').read_text())['applied'] is False
    def fail(request): raise RuntimeError('window gone')
    receiver.apply_request=fail
    atomic_json(tmp_path,'visual-request.json',{'revision':'failed','expires':time.time()+10})
    receiver.poll()
    assert json.loads((tmp_path/'visual-ack.json').read_text())['applied'] is False
