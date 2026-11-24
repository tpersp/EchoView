import pytest
from flask import Flask
from echoview.web import routes
from echoview.live_settings import atomic_json, VisualSettingsReceiver


@pytest.mark.parametrize('applied,code',[(True,200),(False,503)])
def test_identify_is_post_only_and_never_saves_or_restarts(monkeypatch,applied,code):
    cfg={'displays':{'HDMI-1':{'mode':'videos'},'HDMI-2':{'mode':'spotify'}}}
    monkeypatch.setattr(routes,'load_config',lambda:cfg)
    monkeypatch.setattr(routes,'save_config',lambda *a:pytest.fail('Must not save configuration'))
    monkeypatch.setattr(routes,'_save_and_restart',lambda *a:pytest.fail('Must not restart playback'))
    calls=[]
    def request(directory,config,displays,**kwargs):calls.append((config,displays,kwargs));return applied
    monkeypatch.setattr(routes,'request_update',request)
    app=Flask(__name__);app.register_blueprint(routes.main_bp)
    client=app.test_client()
    assert client.get('/identify_displays').status_code==405
    response=client.post('/identify_displays',headers={'Accept':'application/json'})
    assert response.status_code==code
    assert calls==[(cfg,['HDMI-1','HDMI-2'],{'kind':'identify','channel':'identify'})]


def test_identify_channel_does_not_overwrite_pending_visual_changes(tmp_path):
    import time,json
    visual={'revision':'visual','expires':time.time()+10}
    identify={'revision':'identify','expires':time.time()+10}
    atomic_json(tmp_path,'visual-request.json',visual)
    atomic_json(tmp_path,'identify-request.json',identify)
    seen=[]
    receiver=VisualSettingsReceiver(tmp_path,lambda request:seen.append(request['revision']) or True,channel='identify')
    receiver.poll();receiver.poll()
    assert seen==['identify']
    assert json.loads((tmp_path/'visual-request.json').read_text())==visual
    assert not (tmp_path/'visual-ack.json').exists()
    assert json.loads((tmp_path/'identify-ack.json').read_text())['applied'] is True
