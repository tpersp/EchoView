"""Self-contained schedule browser regression. Requires Playwright Chromium.
Run: python tests/browser/check_schedule_editor.py
Uses a temporary local controller; never connects to the Pi or real media.
"""
from pathlib import Path
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

if '--serve' in sys.argv:
    assert os.environ.get('ECHOVIEW_SCHEDULE_FIXTURE')=='1'
    from echoview.web.app import create_app
    from echoview.web import routes
    from echoview import utils
    for folder in ('Photos & GIFs','Videos','Evening, calm'):
        (Path(utils.IMAGE_DIR)/folder).mkdir(parents=True,exist_ok=True)
    app=create_app()
    routes.detect_monitors_extended=lambda:{}
    def apply(cfg):
        utils.save_config(cfg)
        return {'saved':True,'message':'Fixture applied.'},200
    routes._save_and_restart=apply
    app.run(host='127.0.0.1',port=int(sys.argv[-1]))
    raise SystemExit


from playwright.sync_api import sync_playwright,expect

def check(base,config):
    cfg=json.loads(config.read_text())
    cfg['displays']['Display0'].update(mode='scheduled',schedule=[{'time':t,'name':n,'media':m,'folders':f,'shuffle':False} for t,n,m,f in [('06:00','Morning','images',['Photos & GIFs']),('14:00','Afternoon','videos',['Videos']),('18:00','Evening','images',['Evening, calm','Photos & GIFs'])]])
    config.write_text(json.dumps(cfg,indent=2));before=config.read_bytes()
    with sync_playwright() as p:
     b=p.chromium.launch(headless=True,args=['--no-sandbox']);page=b.new_page(locale='en-US',timezone_id='America/Los_Angeles',viewport={'width':1440,'height':1100});errors=[];writes=[]
     page.on('pageerror',lambda e:errors.append(str(e)))
     page.on('request',lambda r:writes.append(r.url) if r.method!='GET' else None)
     page.goto(base+'/',wait_until='domcontentloaded')
     editor=page.locator('.schedule-editor');rows=editor.locator('.schedule-slot')
     assert rows.count()==3
     assert rows.evaluate_all('(rows)=>rows.every(row=>!row.open)')
     assert editor.locator('input[type=time]').count()==0
     expect(rows.nth(0).locator('.schedule-time-badge')).to_have_text('06:00')
     assert '00:00–06:00' in editor.locator('.schedule-day').inner_text()
     row=rows.nth(1);row.locator('summary').click()
     hour=row.get_by_role('spinbutton',name='Hour (00–23)');minute=row.get_by_role('spinbutton',name='Minute (00–59)')
     hour.fill('23');minute.fill('59');expect(row.locator('.schedule-time-badge')).to_have_text('23:59')
     hour.fill('6');minute.fill('00');assert 'Two slots start at 06:00' in editor.locator('.schedule-error').inner_text()
     hour.fill('14');minute.fill('00');expect(editor.locator('.schedule-error')).to_have_text('')
     row.get_by_role('button',name='Edit folders',exact=True).click()
     search=row.get_by_role('searchbox',name='Find folders for this slot');search.fill('Evening')
     row.locator('.schedule-folder-option').click()
     expect(row.locator('.schedule-folder-chips')).to_contain_text('Evening, calm')
     row.get_by_role('button',name='Clear selection',exact=True).click()
     assert 'Choose at least one folder' in editor.locator('.schedule-error').inner_text()
     search.fill('Videos');row.get_by_role('button',name='Select matches',exact=True).click()
     search.fill('Evening');row.get_by_role('button',name='Select matches',exact=True).click()

     assert row.locator('.schedule-folder-menu').evaluate('(el)=>getComputedStyle(el).position')=='static'
     search.fill('no match');expect(row.locator('.schedule-folder-options')).to_contain_text('No matching folders')
     search.fill('');search.press('ArrowDown');page.keyboard.press('Escape');expect(row.locator('.schedule-folder-menu')).to_be_hidden()
     row.get_by_role('button',name='Done editing').click();assert not row.evaluate('(el)=>el.open')
     editor.get_by_role('button',name='Add time slot',exact=True).click();new=rows.last
     assert new.evaluate('(el)=>el.open')
     new.get_by_role('spinbutton',name='Hour (00–23)').fill('0');new.get_by_role('spinbutton',name='Minute (00–59)').fill('00')
     expect(new.locator('.schedule-time-badge')).to_have_text('00:00')
     new.get_by_role('button',name='Choose folders',exact=True).click();new.locator('.schedule-folder-option').filter(has_text='Photos & GIFs').click()
     new.get_by_role('button',name='Done',exact=True).click()
     assert config.read_bytes()==before and not writes
     page.screenshot(path='/tmp/echoview-schedule-editor-desktop.png',full_page=True)
     page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
     page.screenshot(path='/tmp/echoview-schedule-editor-mobile.png',full_page=True)
     page.get_by_role('button',name='Apply to displays',exact=True).click();page.wait_for_load_state('domcontentloaded')
     saved=json.loads(config.read_text())['displays']['Display0']['schedule']
     assert len(saved)==4 and any(entry['time']=='00:00' for entry in saved)
     assert next(e for e in saved if e['time']=='14:00')['folders']==['Videos','Evening, calm']
     assert not errors,errors
     b.close();print('Schedule editor: en-US 24-hour fields, collapsed cards, inline searchable folders, midnight, duplicate validation, keyboard, no premature saves, mobile, persistence passed.')

with tempfile.TemporaryDirectory(prefix='ev-schedule-ui-') as home:
    with socket.socket() as reserved:
        reserved.bind(('127.0.0.1',0));port=reserved.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    root=Path(__file__).resolve().parents[2]
    env=dict(os.environ,VIEWER_HOME=home,IMAGE_DIR=str(Path(home)/'media'),PYTHONPATH=str(root),ECHOVIEW_SCHEDULE_FIXTURE='1')
    process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--serve',str(port)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+10
        while True:
            try:
                urllib.request.urlopen(base+'/schedule/clock',timeout=.5).close();break
            except OSError:
                if process.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Fixture did not start')
                time.sleep(.05)
        check(base,Path(home)/'viewerconfig.json')
    finally:
        process.terminate()
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.kill();process.wait()
