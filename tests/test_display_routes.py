from copy import deepcopy
from pathlib import Path
import subprocess

from flask import Flask
import pytest

from echoview import displays, utils
from echoview.web import routes


@pytest.fixture
def controller(monkeypatch):
    found = displays.parse_xrandr((Path(__file__).parent / "fixtures/displays/xrandr.txt").read_text())
    cfg = {"displays": {"Composite-1": dict(displays.default_display("Composite-1"), chosen_mode="1920x1080"),
                        "HDMI-9": dict(displays.default_display("HDMI-9"), specific_image="saved.png")}}
    saved, applied = [], []
    monkeypatch.setattr(routes, "load_config", lambda: cfg)
    monkeypatch.setattr(routes, "save_config", lambda new: saved.append(deepcopy(new)))
    monkeypatch.setattr(routes, "discover_monitors", lambda: found)
    monkeypatch.setattr(routes, "apply_output_mode", lambda name, selection: applied.append((name, selection)))
    monkeypatch.setattr(routes, "get_system_stats", lambda: (0, 0, 0, 0, "unknown"))
    monkeypatch.setattr(routes, "get_storage_stats", lambda: (0, 0))
    monkeypatch.setattr(routes, "get_hostname", lambda: "fixture")
    monkeypatch.setattr(routes, "get_ip_address", lambda: "fixture")
    monkeypatch.setattr(routes, "get_pi_model", lambda: "fixture")
    monkeypatch.setattr(routes, "get_subfolders", lambda: [])
    monkeypatch.setattr(routes.subprocess, "run", lambda *args, **kwargs: None)
    app = Flask("echoview.web.app", template_folder="templates", static_folder="static")
    app.secret_key = "test"
    app.register_blueprint(routes.main_bp)
    return app.test_client(), cfg, found, saved, applied


def test_actual_modes_and_offline_preferences_are_distinct(controller):
    client, cfg, found, saved, applied = controller
    response = client.get("/")
    assert response.status_code == 200
    assert b"Actual: 720x576i @ 50.00 Hz" in response.data
    assert b"Saved preference: auto" in response.data
    assert b"HDMI-9" in response.data and b"Disconnected / unavailable" in response.data
    assert cfg["displays"]["HDMI-9"]["specific_image"] == "saved.png"
    assert applied == []  # Viewing the page must never change hardware modes.


def test_display_navigation_defers_stats_and_media_scans(controller, monkeypatch):
    client, cfg, found, saved, applied = controller
    def fail(*args, **kwargs):
        pytest.fail('Navigation must defer NAS scans, media inspection and stats sampling')
    monkeypatch.setattr(utils, 'count_files_in_folder', fail)
    monkeypatch.setattr(utils, 'media_aspect_label', fail)
    monkeypatch.setattr(routes, 'get_system_stats', fail)
    monkeypatch.setattr(routes, 'get_storage_stats', fail)
    monkeypatch.setattr(routes.os, 'listdir', fail)
    response = client.get('/')
    assert response.status_code == 200
    assert b'class="specific-picker"' in response.data
    assert b'value="saved.png"' in response.data


def test_list_monitors_uses_actual_connector_data(controller):
    client, cfg, found, saved, applied = controller
    response = client.get("/list_monitors")
    data = response.get_json()
    assert data["Composite-1"]["offset_x"] == -720
    assert data["Composite-1"]["resolution"] == "720x576i"
    assert data["Composite-1"]["available_modes"][0]["value"] == "720x576i@50.00"
    assert data["HDMI-2"]["connected"] is False
    assert "Display0" not in data


def test_output_preferences_saved_only_after_success(controller):
    client, cfg, found, saved, applied = controller
    response = client.post("/display/output", data={"display": "Composite-1", "output_mode": "720x576i@50.00", "display_aspect": "4:3"})
    assert response.status_code == 302
    assert applied == [("Composite-1", "720x576i@50.00")]
    assert saved[-1]["displays"]["Composite-1"]["display_aspect"] == "4:3"
    assert saved[-1]["displays"]["Composite-1"]["output_mode"] == "720x576i@50.00"


def test_failed_mode_change_does_not_save_new_preferences(controller, monkeypatch):
    client, cfg, found, saved, applied = controller
    before = deepcopy(cfg)
    def fail(*args):
        raise ValueError("Mode unavailable")
    monkeypatch.setattr(routes, "apply_output_mode", fail)
    assert client.post("/display/output", data={"display": "Composite-1", "output_mode": "1920x1080@60.00", "display_aspect": "16:9"}).status_code == 400
    assert not saved and cfg == before


def test_invalid_aspect_and_unknown_display_never_change_output(controller):
    client, cfg, found, saved, applied = controller
    for data in ({"display": "Composite-1", "display_aspect": "invalid"}, {"display": "unknown"}):
        assert client.post("/display/output", data=data).status_code == 400
    assert not saved and not applied


def test_saved_settings_and_restart_failure_reported_separately(controller, monkeypatch):
    client, cfg, found, saved, applied = controller
    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired("systemctl", 10)
    monkeypatch.setattr(routes.subprocess, "run", fail)
    client.post("/display/output", data={"display": "Composite-1", "display_aspect": "4:3"})
    response = client.get("/")
    assert b"restart the viewer" in response.data
    assert saved[-1]["displays"]["Composite-1"]["display_aspect"] == "4:3"


def test_migration_does_not_activate_legacy_display_only_resolution():
    cfg = {"displays": {"HDMI-1": {"chosen_mode": "1920x1080"}}}
    utils.upgrade_config(cfg)
    assert cfg["displays"]["HDMI-1"]["chosen_mode"] == "1920x1080"
    assert cfg["displays"]["HDMI-1"]["output_mode"] == "auto"


def test_presentation_controls_do_not_change_output_mode(controller):
    client, cfg, found, saved, applied = controller
    response = client.post("/display/presentation", data={"display": "HDMI-9", "safe_left": "5", "safe_bottom": "7.5", "resource_profile": "pi3"})
    assert response.status_code == 302
    assert not applied  # Safe-area settings also work while the output is offline.
    result = saved[-1]["displays"]["HDMI-9"]
    assert result["safe_area"] == {"left": 5, "right": 0, "top": 0, "bottom": 7.5}
    assert "resource_profile" not in result
    assert result["output_mode"] == "auto" and result["specific_image"] == "saved.png"


@pytest.mark.parametrize("data", [{"safe_top": "nan"}, {"safe_right": "-1"}, {"safe_bottom": "21"}])
def test_invalid_presentation_input_does_not_save_or_apply(controller, data):
    client, cfg, found, saved, applied = controller
    before = deepcopy(cfg)
    response = client.post("/display/presentation", data={"display": "Composite-1", **data})
    assert response.status_code == 400
    assert not saved and not applied and cfg == before


def test_presentation_page_has_calibration_and_safe_area_controls(controller):
    client, cfg, found, saved, applied = controller
    response = client.get("/")
    assert response.status_code == 200
    assert b'name="resource_profile"' not in response.data
    assert b'value="calibration"' in response.data
    assert b'name="safe_left"' in response.data


def test_overlay_frame_is_read_only_private_and_validates_display(controller, monkeypatch):
    from echoview import overlay_preview
    client, cfg, found, saved, applied = controller
    calls = []
    monkeypatch.setattr(overlay_preview, 'request_frame', lambda directory, display: calls.append(display) or b'jpeg')
    response = client.get('/overlay_preview/Composite-1')
    assert response.status_code == 200 and response.data == b'jpeg'
    assert response.mimetype == 'image/jpeg'
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert client.get('/overlay_preview/unknown').status_code == 404
    assert calls == ['Composite-1'] and not saved and not applied
    monkeypatch.setattr(overlay_preview, 'request_frame', lambda *a: (_ for _ in ()).throw(overlay_preview.PreviewUnavailable()))
    assert client.get('/overlay_preview/Composite-1').status_code == 503


def test_invalid_clock_font_size_is_rejected_without_saving(controller):
    client, cfg, found, saved, applied = controller
    response = client.post("/overlay_config", data={"Composite-1_clock_font_size": "nan"})
    assert response.status_code == 400
    assert not saved


def test_youtube_fallback_is_real_http_page_with_referer_origin(controller):
    from urllib.parse import parse_qs, urlparse
    from html.parser import HTMLParser
    client, cfg, found, saved, applied = controller
    cfg["displays"]["Composite-1"].update(web_url="https://youtu.be/abc123def45", youtube_mute=False, youtube_autoplay=False)
    response = client.get("/player/youtube?display=Composite-1")
    assert response.status_code == 200
    sources = []
    class Parser(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag == "iframe":
                sources.append(dict(attrs))
    Parser().feed(response.get_data(as_text=True))
    query = parse_qs(urlparse(sources[0]["src"]).query)
    assert query["origin"] == ["http://localhost"]
    assert query["mute"] == query["autoplay"] == ["0"]
    assert sources[0]["referrerpolicy"] == "strict-origin-when-cross-origin"


def test_player_route_rejects_non_youtube_and_unknown_displays(controller):
    client, cfg, found, saved, applied = controller
    cfg["displays"]["Composite-1"]["web_url"] = "https://example.invalid/private"
    assert client.get("/player/youtube?display=Composite-1").status_code == 400
    assert client.get("/player/youtube?display=unknown").status_code == 404


def test_saving_web_url_does_not_do_network_extraction(controller, monkeypatch):
    from echoview import embed_utils
    client, cfg, found, saved, applied = controller
    monkeypatch.setattr(embed_utils.requests, "get", lambda *a, **kw: pytest.fail("save network request"))
    monkeypatch.setattr(routes.subprocess, "check_call", lambda *a, **kw: None)
    response = client.post("/", data={"action": "update_displays", "Composite-1_mode": "web_page", "Composite-1_web_url": "https://youtube.com/watch?v=abc123def45"})
    assert response.status_code == 302
    assert saved[-1]["displays"]["Composite-1"]["embed_metadata"]["embed_type"] == "youtube"


def overlay_form(cfg):
    data={}
    for name,display in cfg['displays'].items():
        over=display.get('overlay',{})
        for key,default in [('clock_font_size',26),('font_color','#FFFFFF'),('clock_position','bottom-center')]:
            data[name+'_'+key]=str(over.get(key,default))
        for key in ('clock_enabled','auto_negative_font'):
            if over.get(key): data[name+'_'+key]='on'
    return data


def test_overlay_live_apply_preserves_playback_and_legacy_settings(controller,monkeypatch):
    client,cfg,found,saved,applied=controller
    cfg['overlay']={'offset_x':20,'offset_y':30}
    for display in cfg['displays'].values():
        display['overlay']={'clock_enabled':False,'clock_font_size':26,'font_color':'#FFFFFF',
                            'auto_negative_font':False,'clock_position':'bottom-center','custom':'preserved'}
    before=deepcopy(cfg); requests=[]
    monkeypatch.setattr(routes,'apply_live_settings',lambda cfg,names,kind:requests.append((names,kind)) or True)
    monkeypatch.setattr(routes.subprocess,'run',lambda *a,**k:pytest.fail('restart'))
    monkeypatch.setattr(routes.subprocess,'check_call',lambda *a,**k:pytest.fail('restart'))
    data=overlay_form(cfg); data.update({'Composite-1_clock_enabled':'on','Composite-1_clock_font_size':'30'})
    response=client.post('/overlay_config',data=data,follow_redirects=True)
    assert response.status_code==200 and b'Overlay settings applied. Playback kept running.' in response.data
    assert requests==[(['Composite-1'],'overlay')]
    assert saved[-1]['overlay']==before['overlay']
    assert saved[-1]['displays']['Composite-1']['overlay']['custom']=='preserved'
    for name in cfg['displays']:
        assert {k:v for k,v in saved[-1]['displays'][name].items() if k!='overlay'}=={k:v for k,v in before['displays'][name].items() if k!='overlay'}


def test_overlay_noop_does_not_save_or_signal(controller,monkeypatch):
    client,cfg,found,saved,applied=controller
    for display in cfg['displays'].values():
        display['overlay']={'clock_enabled':False,'clock_font_size':26,'font_color':'#FFFFFF',
                            'auto_negative_font':False,'clock_position':'bottom-center'}
    monkeypatch.setattr(routes,'apply_live_settings',lambda *a,**k:pytest.fail('no-op signal'))
    assert client.post('/overlay_config',data=overlay_form(cfg)).status_code==302
    assert not saved


def test_overlay_unconfirmed_save_is_reported_without_restart(controller,monkeypatch):
    client,cfg,found,saved,applied=controller
    monkeypatch.setattr(routes,'apply_live_settings',lambda *a,**k:False)
    monkeypatch.setattr(routes.subprocess,'check_call',lambda *a,**k:pytest.fail('restart'))
    data=overlay_form(cfg);data['Composite-1_clock_enabled']='on'
    response=client.post('/overlay_config',data=data,follow_redirects=True)
    assert b'live update could not be confirmed' in response.data
    assert saved[-1]['displays']['Composite-1']['overlay']['clock_enabled'] is True


def test_invalid_overlay_position_never_saves(controller):
    client,cfg,found,saved,applied=controller
    before=deepcopy(cfg);data=overlay_form(cfg);data['Composite-1_clock_position']='invalid'
    assert client.post('/overlay_config',data=data).status_code==400
    assert not saved and cfg==before


@pytest.mark.parametrize('name,display,monitor,ratio',[
    ('HDMI-1',{}, {'current_mode':'1920x1080'},16/9),
    ('Composite-1',{'display_aspect':'auto'},{'current_mode':'720x576i'},4/3),
    ('HDMI-2',{'display_aspect':'9:16'},{'current_mode':'1080x1920'},9/16),
])
def test_clock_preview_matches_physical_screen_shape(name,display,monitor,ratio):
    geometry=routes.clock_preview_geometry(display,name,monitor)
    assert geometry['aspect']==pytest.approx(ratio)
    assert geometry['width']>0 and geometry['height']>0


def test_clock_preview_fallback_and_safe_area():
    geometry=routes.clock_preview_geometry({'safe_area':{'left':10,'top':5}},'HDMI-1',{})
    assert geometry['width']==1920 and geometry['height']==1080
    assert geometry['safe_area']['left']==10 and geometry['safe_area']['top']==5


@pytest.mark.parametrize('clock_format,seconds',[('12',False),('12',True),('24',False),('24',True)])
def test_clock_format_saves_live_per_display(controller,monkeypatch,clock_format,seconds):
    client,cfg,found,saved,applied=controller
    requests=[]
    monkeypatch.setattr(routes,'apply_live_settings',lambda cfg,names,kind:requests.append(kind) or True)
    data=overlay_form(cfg);data['Composite-1_clock_format']=clock_format
    if seconds:data['Composite-1_clock_show_seconds']='on'
    assert client.post('/overlay_config',data=data).status_code==302
    over=saved[-1]['displays']['Composite-1']['overlay']
    assert over.get('clock_format','24')==clock_format
    assert over.get('clock_show_seconds',True)==seconds
    assert requests==['overlay']


def test_cached_form_keeps_existing_clock_format(controller,monkeypatch):
    client,cfg,found,saved,applied=controller
    cfg['displays']['Composite-1']['overlay']={'clock_format':'12','clock_show_seconds':False}
    monkeypatch.setattr(routes,'apply_live_settings',lambda *a,**k:True)
    assert client.post('/overlay_config',data=overlay_form(cfg)).status_code==302
    over=saved[-1]['displays']['Composite-1']['overlay']
    assert over['clock_format']=='12' and over['clock_show_seconds'] is False


def test_invalid_clock_format_preserves_config(controller):
    client,cfg,found,saved,applied=controller
    before=deepcopy(cfg);data=overlay_form(cfg);data['Composite-1_clock_format']='invalid'
    assert client.post('/overlay_config',data=data).status_code==400
    assert not saved and cfg==before


def test_clock_blink_toggle_live_and_cached_form_preserves_it(controller,monkeypatch):
    client,cfg,found,saved,applied=controller
    monkeypatch.setattr(routes,'apply_live_settings',lambda *a,**k:True)
    data=overlay_form(cfg);data.update({'Composite-1_clock_blink_present':'1','Composite-1_clock_blink_separators':'on'})
    assert client.post('/overlay_config',data=data).status_code==302
    assert saved[-1]['displays']['Composite-1']['overlay']['clock_blink_separators'] is True
    cfg['displays']['Composite-1']['overlay']=saved[-1]['displays']['Composite-1']['overlay']
    assert client.post('/overlay_config',data=overlay_form(cfg)).status_code==302
    # A cached form does not turn the feature off.
    assert saved[-1]['displays']['Composite-1']['overlay']['clock_blink_separators'] is True
    assert cfg['displays']['Composite-1']['overlay']['clock_blink_separators'] is True
    del data['Composite-1_clock_blink_separators']
    assert client.post('/overlay_config',data=data).status_code==302
    assert saved[-1]['displays']['Composite-1']['overlay']['clock_blink_separators'] is False
