"""Browser recovery checks with mocked status/restart responses; never restarts a real viewer.

Run against a synthetic controller fixture: python tests/browser/check_recovery.py --url http://localhost:8088
Requires Playwright and Chromium.
"""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:8088');args=parser.parse_args();base=args.url.rstrip('/')
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,args=['--no-sandbox']);page=b.new_page(viewport={'width':1440,'height':1100});errors=[];writes=[];requests=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.on('request',lambda r:writes.append(r.url) if r.method!='GET' else None)
 state={'viewer':100,'issues':[]};restart_fail=[False]
 def status(route):requests.append(route.request.url);route.fulfill(json=state)
 def restart(route):
  assert route.request.method=='POST'
  if restart_fail[0]:route.fulfill(status=503,json={'error':'Viewer restart could not be confirmed. Check the service logs.'})
  else:state.update(viewer=102 if state['viewer'] is None else 101,issues=[]);route.fulfill(status=202,json={'message':'Viewer restart requested. Waiting for playback status.'})
 page.route('**/recovery_status',status);page.route('**/restart_viewer',restart)
 page.goto(base+'/',wait_until='domcontentloaded')
 panel=page.locator('[data-recovery-panel]');expect(panel).to_be_hidden()
 mode=page.locator('.display-mode select').first;prefix=mode.get_attribute('name')[:-5];mode.select_option('spotify')
 form=page.locator('[name="'+prefix+'_spotify_font_size"]');form.fill('31')
 state['issues']=[dict(code='storage_missing',title='Media storage is disconnected',detail='Reconnect storage before restarting the viewer.',action='retry',display=''),dict(code='spotify_auth',title='Spotify needs authorization',detail='Reconnect your Spotify account.',action='spotify',display='<img src=x onerror=alert(1)>')]
 page.wait_for_timeout(5100);expect(panel).to_be_visible()
 assert panel.locator('img').count()==0
 expect(panel.get_by_role('link',name='Spotify settings')).to_have_attribute('href','/configure_spotify')
 panel.screenshot(path='/tmp/echoview-recovery-panel.png')
 page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
 panel.get_by_role('button',name='Restart viewer').click()
 expect(panel).to_be_hidden(timeout=8000);assert form.input_value()=='31'
 assert len(writes)==1 and writes[0].endswith('/restart_viewer')
 state.update(viewer=101,issues=[dict(code='viewer_unavailable',title='Viewer status is unavailable',detail='The viewer may be starting or not responding.',action='restart',display='')])
 page.wait_for_timeout(5100);expect(panel).to_be_visible();restart_fail[0]=True
 panel.get_by_role('button',name='Restart viewer').click()
 expect(panel.locator('[data-recovery-feedback]')).to_contain_text('could not be confirmed')
 expect(panel.get_by_role('button',name='Restart viewer')).to_be_enabled()
 state['issues']=[];panel.get_by_role('button',name='Check again').click();expect(panel).to_be_hidden()
 state.update(viewer=None,issues=[dict(code='viewer_unavailable',title='Viewer status is unavailable',detail='The viewer may be starting or not responding.',action='restart',display='')])
 page.wait_for_timeout(5100);expect(panel).to_be_visible();restart_fail[0]=False
 panel.get_by_role('button',name='Restart viewer').click();expect(panel).to_be_hidden(timeout=8000)

 page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});document.dispatchEvent(new Event('visibilitychange'))")
 count=len(requests);page.wait_for_timeout(5200);assert len(requests)==count
 page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>false});document.dispatchEvent(new Event('visibilitychange'))")
 page.wait_for_timeout(250);assert len(requests)>count
 page.goto(base+'/status',wait_until='domcontentloaded')
 expect(page.locator('[data-recovery-panel]')).to_be_visible()
 expect(page.locator('.recovery-healthy')).to_contain_text('Viewer is responding')
 expect(page.locator('a.nav-link.active')).to_have_text('Status')
 assert not errors,errors
 b.close();print('Recovery UI: healthy hidden, current faults, safe text, actions, explicit restart confirmation, failure/retry, preserved unsaved settings, mobile, hidden-tab pause passed.')
