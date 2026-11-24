// Layout previews are browser-only and read the viewer's existing local snapshot.
document.addEventListener('DOMContentLoaded', () => {
  const previews = [...document.querySelectorAll('.spotify-preview')];
  if (!previews.length) return;
  let sample = null, timer, controller;
  const example = {song: 'Song title', artist: 'Artist name', album: 'Album name', device_name: 'Living room', progress_ms: 60000, duration_ms: 180000, art_colors: ['#4e6f86','#162d45']};
  for (const control of document.querySelectorAll('[data-background-dim]')) {
    const update = () => { control.closest('label').querySelector('output').textContent = control.value+'%'; };
    control.addEventListener('input',update); update();
  }
  function active() { return previews.some(preview => preview.open && preview.closest('.mode-section').style.display !== 'none'); }
  function render(preview) {
    const form = preview.closest('form'), prefix = preview.dataset.display + '_';
    const value = (key, fallback) => form.elements.namedItem(prefix + key)?.value ?? fallback;
    const enabled = (key, fallback) => form.elements.namedItem(prefix + key)?.checked ?? fallback;
    const screen = preview.querySelector('[data-preview-screen]');
    const layout = value('spotify_layout', 'classic');
    let [width, height] = (preview.dataset.resolution.match(/\d+/g) || ['1280','720']).map(Number);
    if (!width || !height) { width = 1280; height = 720; }
    const aspect = value('display_aspect', preview.dataset.aspect);
    const ratio = /^\d+:\d+$/.test(aspect) ? aspect.split(':').map(Number).reduce((a,b) => a/b) : width/height;
    screen.style.aspectRatio = String(ratio || 16/9);
    screen.dataset.layout = layout;
    screen.classList.toggle('portrait', ratio < 1.2);
    const data = sample && ['playing','paused'].includes(sample.status) ? sample : example;
    const backgroundMode = value('spotify_background_mode','black');
    const dim = Math.max(0,Math.min(95,Number(value('spotify_background_dim',65))));
    const raw = (Array.isArray(data.art_colors) ? data.art_colors : []).filter(c => /^#[0-9a-f]{6}$/i.test(c));
    const palette = raw.length ? [raw[0],raw[1] || raw[0]] : ['#263449','#171f2c'];
    const colours = palette.map(c => '#'+[1,3,5].map(i => Math.round(parseInt(c.slice(i,i+2),16)*(100-dim)/100).toString(16).padStart(2,'0')).join(''));
    if (backgroundMode!=='gradient') colours[1]=colours[0];
    screen.style.background = backgroundMode==='gradient' ? `linear-gradient(90deg,${colours[0]},${colours[1]})` : backgroundMode==='artwork' ? colours[0] : '#000000';
    const blur = preview.querySelector('.spotify-preview-blur');
    blur.hidden = !(backgroundMode==='blurred' || (layout==='classic' && backgroundMode==='black')) || !data.artwork;
    blur.style.backgroundImage = blur.hidden ? 'none' : `url(${JSON.stringify(data.artwork)})`;
    blur.style.filter = `blur(${Math.max(2,screen.clientWidth*8/96)}px) brightness(${(100-dim)/100})`;
    if (layout==='classic' && backgroundMode==='black') blur.style.filter = `blur(${Number(preview.dataset.blurRadius || 0)*screen.clientWidth/width}px)`;
    for (const name of ['song','artist','album','device']) {
      const node = preview.querySelector(`[data-preview-${name}]`);
      const text = name === 'device' ? (data.device_name ? `Playing on ${data.device_name}` : '') : data[name] || '';
      node.textContent = enabled('spotify_show_' + name, name !== 'device') ? text.replace(/\s+/g,' ').trim() : '';
      node.hidden = !node.textContent;
    }
    const image = preview.querySelector('img');
    if (data.artwork) {
      if (image.getAttribute('src') !== data.artwork) image.src = data.artwork;
      image.hidden = false;
    } else { image.hidden = true; image.removeAttribute('src'); }
    const scale = Math.max(.1, screen.clientHeight / height);
    screen.style.setProperty('--preview-font', `${Math.max(5, (Number(value('spotify_font_size',18)) || 18)*scale)}px`);
    let textColour = '#edf2f7';
    if (['artwork','gradient'].includes(backgroundMode) && layout!=='classic') {
      const luminance = c => [1,3,5].map(i => parseInt(c.slice(i,i+2),16)/255).map(v => v<=.04045 ? v/12.92 : ((v+.055)/1.055)**2.4).reduce((sum,v,i) => sum+v*[.2126,.7152,.0722][i],0);
      const levels=colours.map(luminance);
      if (Math.min(...levels.map(v => (v+.05)/(luminance('#101620')+.05))) > Math.min(...levels.map(v => 1.05/(v+.05)))) textColour='#101620';
    }
    screen.style.setProperty('--preview-color', enabled('spotify_negative_font',true) ? textColour : value('spotify_font_color','#ffffff'));
    screen.classList.toggle('automatic-contrast', enabled('spotify_negative_font',true));
    screen.dataset.position = value('spotify_info_position','bottom-center');
    const bar = preview.querySelector('.spotify-preview-progress');
    bar.hidden = !enabled('spotify_show_progress',false);
    const palettes = {dark:['#333','#888'], light:['#f0f0f0','#a0a0a0'], spotify:['#121212','#1db954'], coffee:['#423828','#8b4513']};
    const colors = palettes[value('spotify_progress_theme','dark')] || palettes.dark;
    bar.style.background = colors[0]; bar.firstElementChild.style.background = colors[1];
    bar.firstElementChild.style.width = `${data.duration_ms > 0 ? Math.min(100, data.progress_ms/data.duration_ms*100) : 0}%`;
    const pos = value('spotify_progress_position','bottom-center');
    bar.classList.toggle('at-top', layout === 'classic' && ['above_info','top-center'].includes(pos));
    const timing = preview.querySelector('[data-preview-time]');
    const clock = ms => {
      const seconds = Math.floor(Math.max(0, ms || 0) / 1000);
      const h = Math.floor(seconds / 3600), m = Math.floor(seconds / 60) % 60, s = seconds % 60;
      return h ? `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}` : `${m}:${String(s).padStart(2,'0')}`;
    };
    timing.hidden = !enabled('spotify_show_time',false);
    timing.textContent = data.duration_ms > 0 ? `${clock(Math.min(data.duration_ms, data.progress_ms))}/${clock(data.duration_ms)}` : '0:00/–:––';
    timing.classList.toggle('at-top', bar.classList.contains('at-top'));
    timing.classList.toggle('time-only', !enabled('spotify_show_progress',false));
    bar.style.right = timing.hidden ? '4%' : '30%';
    if (layout==='classic') renderClassic(preview,screen,image,width,height,ratio,value,enabled);
    else {
      for (const node of preview.querySelectorAll('.spotify-preview-art,.spotify-preview-art img,.spotify-preview-info,.spotify-preview-info > div')) node.removeAttribute('style');
      bar.style.top=''; bar.style.left=''; bar.style.bottom=''; bar.style.height=''; bar.style.width='';bar.style.borderRadius='';bar.style.border='';bar.style.boxSizing='';
      timing.removeAttribute('style');preview.querySelector('.spotify-preview-info').hidden=false;
    }
    preview.querySelector('[data-preview-note]').textContent = data === example ? 'Example track' : 'Now playing';
  }
  function renderClassic(preview,screen,image,width,height,ratio,value,enabled) {
    const sx=screen.clientWidth/width, sy=screen.clientHeight/height;
    if (!sx || !sy) return;
    const margins=JSON.parse(preview.dataset.safeArea || '{}') || {};
    const edge=name => Math.round((name==='left'||name==='right'?width:height)*(Number(margins[name])||0)/100);
    const safe={x:edge('left'),y:edge('top'),w:width-edge('left')-edge('right'),h:height-edge('top')-edge('bottom')};
    const pixelAspect=ratio/(width/height);
    const iw=image.naturalWidth || 1, ih=image.naturalHeight || 1;
    const angle=Number(value('rotate',0))*Math.PI/180;
    const rw=Math.abs(iw*Math.cos(angle))+Math.abs(ih*Math.sin(angle));
    const rh=Math.abs(iw*Math.sin(angle))+Math.abs(ih*Math.cos(angle));
    const factor=Math.min(safe.w*pixelAspect/rw,safe.h/rh);
    const art={w:Math.round(rw*factor/pixelAspect),h:Math.round(rh*factor)};
    art.x=safe.x+Math.floor((safe.w-art.w)/2);art.y=safe.y+Math.floor((safe.h-art.h)/2);
    const box=(node,rect) => {
      Object.assign(node.style,{left:`${rect.x*sx}px`,top:`${rect.y*sy}px`,width:`${rect.w*sx}px`,height:`${rect.h*sy}px`,right:'auto',bottom:'auto'});
    };
    const artwork=preview.querySelector('.spotify-preview-art');box(artwork,art);
    // Rotate before correcting the output's physical pixel aspect, as Qt does.
    Object.assign(image.style,{left:'50%',top:'50%',right:'auto',bottom:'auto',width:`${iw*factor*sy}px`,height:`${ih*factor*sy}px`,maxWidth:'none',transform:`translate(-50%,-50%) scaleX(${sx/(sy*pixelAspect)}) rotate(${angle}rad)`});
    const info=preview.querySelector('.spotify-preview-info');
    const rows=[...info.children].filter(node=>!node.hidden);
    info.hidden=!rows.length;
    const font=Math.max(8,Math.min(Math.max(8,Math.min(512,Math.floor(safe.h/4))),Math.trunc(Number(value('spotify_font_size',18)))||18));
    const factors=[1.25,1,.85,.75];
    const rowHeight=node=>Math.round(Math.max(1,Math.round(font*factors[[...info.children].indexOf(node)]))*1.4);
    const position=value('spotify_info_position','bottom-center');
    const hasProgress=enabled('spotify_show_progress',false)||enabled('spotify_show_time',false);
    const ppos=value('spotify_progress_position','below_info');
    const reserve=hasProgress && safe.h>40 ? (enabled('spotify_show_time',false)?Math.max(10,Math.min(32,font))+13:15):0;
    const area={...art};
    if (['above_info','top-center'].includes(ppos)) area.y+=reserve;
    area.h=Math.max(1,area.h-reserve);
    const margin=Math.min(10,Math.floor(area.w/10),Math.floor(area.h/10));
    const panel={w:Math.max(1,area.w-2*margin),h:Math.max(1,Math.min(rows.length?16+rows.reduce((total,node)=>total+rowHeight(node),0):0,Math.max(1,area.h-2*margin)))};
    panel.x=area.x+margin;panel.y=position.includes('top')?area.y+margin:area.y+area.h-panel.h-margin;
    box(info,panel);
    const manual=value('spotify_font_color','#ffffff');
    const rgb=[1,3,5].map(i=>parseInt(manual.slice(i,i+2),16));
    const dark=!enabled('spotify_negative_font',true) && (Math.max(...rgb)+Math.min(...rgb))/2<128;
    info.style.background=dark?'rgba(255,255,255,0.824)':'rgba(0,0,0,0.722)';
    info.style.color=enabled('spotify_negative_font',true)?'#edf2f7':manual;
    info.style.textAlign=position.includes('left')?'left':position.includes('right')?'right':'center';
    info.style.padding=`${8*sy}px ${8*sx}px`;info.style.borderRadius=`${8*sy}px / ${8*sx}px`;
    const shrink=Math.min(1,Math.max(1,panel.h-16)/Math.max(1,rows.reduce((total,node)=>total+rowHeight(node),0)));
    for (const node of rows) {
      const index=[...info.children].indexOf(node), size=Math.max(1,Math.round(font*factors[index]*shrink));
      node.style.fontSize=`${size*sy}px`;node.style.lineHeight=`${Math.round(size*1.4)*sy}px`;
    }
    const bar=preview.querySelector('.spotify-preview-progress'), timing=preview.querySelector('[data-preview-time]');
    const m=Math.min(10,Math.floor(safe.w/10),Math.floor(safe.h/10));
    const barHeight=Math.min(enabled('spotify_show_time',false)?Math.max(10,Math.min(32,font))+8:10,Math.max(1,safe.h-2*m));
    let y=ppos==='above_info'?panel.y-barHeight-5:ppos==='below_info'?panel.y+panel.h+5:ppos==='top-center'?safe.y+m:safe.y+safe.h-barHeight-m;
    y=Math.max(safe.y+m,Math.min(safe.y+safe.h-barHeight-m,y));
    box(bar,{x:safe.x+m,y:y+(enabled('spotify_show_time',false)?(barHeight-10)/2:0),w:Math.max(1,safe.w-2*m),h:enabled('spotify_show_time',false)?10:barHeight});
    bar.style.borderRadius=`${5*sy}px`;bar.style.border=`${sy}px solid ${value('spotify_progress_theme','dark')==='spotify'?'#1db954':value('spotify_progress_theme','dark')==='light'?'#cccccc':value('spotify_progress_theme','dark')==='coffee'?'#8b4513':'#444444'}`;bar.style.boxSizing='border-box';
    // Native progress renders the time in the same bounds, beside the bar.
    const timeWidth=Math.min(safe.w-2*m,(timing.textContent.length*font*.62+12));
    if (!timing.hidden) {
      box(timing,{x:enabled('spotify_show_progress',false)?safe.x+safe.w-m-timeWidth:safe.x+(safe.w-timeWidth)/2,y,w:timeWidth,h:barHeight});
      timing.style.fontSize=`${Math.max(10,Math.min(32,font))*sy}px`;timing.style.transform='none';timing.style.padding='0';
      if (!bar.hidden) bar.style.width=`${Math.max(1,safe.w-2*m-timeWidth-8)*sx}px`;
    }
  }
  function renderAll() { previews.filter(preview => preview.open).forEach(render); }
  async function refresh() {
    clearTimeout(timer); timer = null;
    if (document.hidden || !active() || controller) return;
    const request = new AbortController(); controller = request;
    const timeout = setTimeout(() => request.abort(), 8000);
    try {
      const response = await fetch(previews[0].dataset.url, {cache:'no-store',signal:request.signal});
      if (response.ok) { sample = await response.json(); renderAll(); }
    } catch (_) { /* A local example keeps previewing available while offline. */ }
    finally {
      clearTimeout(timeout);
      if (controller === request) { controller = null; if (!document.hidden && active()) timer = setTimeout(refresh,5000); }
    }
  }
  for (const preview of previews) {
    preview.addEventListener('toggle', () => { if (preview.open) render(preview); refresh(); });
    preview.querySelector('img').addEventListener('load', () => { if (preview.open) render(preview); });
    preview.querySelector('img').addEventListener('error', event => { event.target.hidden = true; });
    preview.closest('form').addEventListener('input', renderAll);
    preview.closest('form').addEventListener('change', () => {
      renderAll();
      if (!active()) { clearTimeout(timer); timer = null; }
      else if (!timer && !controller) refresh();
    });
    new ResizeObserver(() => { if (preview.open) render(preview); }).observe(preview);
  }
  document.addEventListener('visibilitychange', () => {
    clearTimeout(timer); controller?.abort(); controller = null;
    if (!document.hidden) refresh();
  });
});
