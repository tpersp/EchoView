"""Compare the DOM-only preview to check_clock_preview.py measurements.

Usage: python tests/browser/check_clock_preview.py /path/to/echoview-clock-geometry.json --url http://localhost:8080
Requires Playwright and Chromium; never submits settings.
"""
import argparse
import json,re
from pathlib import Path
from playwright.sync_api import sync_playwright
parser=argparse.ArgumentParser()
parser.add_argument('geometry',type=Path)
parser.add_argument('--url',default='http://127.0.0.1:8080')
args=parser.parse_args()
rows=json.loads(args.geometry.read_text())
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,args=['--no-sandbox']);page=b.new_page(viewport={'width':1440,'height':1200});errors=[];writes=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.on('request',lambda r:writes.append(r.url) if r.method!='GET' else None)
 def fixed_time(route):
  response=route.fetch();text=response.text();text=re.sub(r'data-clock-seconds="[^"]*"','data-clock-seconds="86339"',text);route.fulfill(response=response,body=text)
 page.route('**/overlay_config',fixed_time)
 page.goto(args.url.rstrip('/')+'/overlay_config',wait_until='domcontentloaded');page.evaluate('document.fonts.ready');page.wait_for_timeout(500)
 assert page.evaluate('document.fonts.check(\'26px "EchoView Clock"\')')
 preview=page.locator('[data-overlay-preview]').first
 maximum=0
 for row in rows:
  actual=preview.evaluate('''(el,row)=>{
    const form=el.closest('form'),prefix=el.dataset.display+'_';
    const set=(key,val)=>{const field=form.elements.namedItem(prefix+key);if(typeof val==='boolean')field.checked=val;else field.value=String(val)};
    el.dataset.geometry=JSON.stringify(row);
    set('clock_enabled',true);set('clock_font_size',row.requested);set('clock_format',row.format);set('clock_show_seconds',row.seconds);set('clock_position',row.position);
    form.dispatchEvent(new Event('input',{bubbles:true}));
    const screen=el.querySelector('[data-overlay-screen]'),clock=el.querySelector('[data-overlay-clock]');
    const s=screen.getBoundingClientRect(),c=clock.getBoundingClientRect(),sx=screen.clientWidth/row.width,sy=screen.clientHeight/row.height;
    return {font:parseFloat(getComputedStyle(clock).fontSize)/sy,bounds:[(c.x-s.x-screen.clientLeft)/sx,(c.y-s.y-screen.clientTop)/sy,c.width/sx,c.height/sy]};
  }''',row)
  assert abs(actual['font']-row['font'])<.1,(row,actual)
  gap=max(abs(a-b) for a,b in zip(actual['bounds'],row['bounds']));maximum=max(maximum,gap)
  assert gap<max(2.1,row["bounds"][2]*.01),(gap,row,actual)
 page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
 assert not errors,errors;assert not writes,writes
 b.close();print('Clock preview/native parity:',len(rows),'cases; max geometry difference',round(maximum,2),'native pixels; mobile, no writes or JS errors.')
