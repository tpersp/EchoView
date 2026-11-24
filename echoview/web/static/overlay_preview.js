// Clock edits stay local; background frames come from the running viewer.
document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('overlay-settings-form');
  const previews = [...document.querySelectorAll('[data-overlay-preview]')];
  if (!form || !previews.length) return;
  const sampled = performance.now();
  const startSeconds = Number(form.dataset.clockSeconds) || 0;
  const fraction = Date.parse(form.dataset.clockIso || '') % 1000 || 0;
  const context=document.createElement('canvas').getContext('2d');
  context.textRendering='geometricPrecision';
  const elapsedMillis = () => startSeconds*1000 + fraction + performance.now()-sampled;
  function clockText(format, showSeconds) {
    const seconds = Math.floor(elapsedMillis()/1000) % 86400;
    const hour = Math.floor(seconds/3600);
    const twelve = format === '12';
    const parts = [twelve ? String(hour%12 || 12) : String(hour).padStart(2,'0'), String(Math.floor(seconds/60)%60).padStart(2,'0')];
    if (showSeconds) parts.push(String(seconds%60).padStart(2,'0'));
    return parts.join(':') + (twelve ? (hour>=12 ? ' PM' : ' AM') : '');
  }
  function render(preview) {
    const prefix = preview.dataset.display + '_';
    const value = (key,fallback) => form.elements.namedItem(prefix+key)?.value ?? fallback;
    const checked = (key,fallback=false) => form.elements.namedItem(prefix+key)?.checked ?? fallback;
    const screen = preview.querySelector('[data-overlay-screen]');
    const safe = preview.querySelector('[data-overlay-safe]');
    const clock = preview.querySelector('[data-overlay-clock]');
    const geometry = JSON.parse(preview.dataset.geometry);
    screen.style.aspectRatio = String(geometry.aspect);
    const margins = geometry.safe_area;
    safe.style.inset = `${margins.top}% ${margins.right}% ${margins.bottom}% ${margins.left}%`;
    safe.classList.toggle('has-safe-area', Object.values(margins).some(value => value>0));
    const show = checked('clock_enabled');
    clock.hidden = !show;
    preview.querySelector('[data-overlay-empty]').hidden = show;
    const auto = checked('auto_negative_font');
    clock.style.color = auto ? '#ffffff' : value('font_color','#ffffff');
    clock.classList.toggle('auto-contrast', auto);
    const text = clockText(value('clock_format','24'),checked('clock_show_seconds',true));
    if (clock.textContent !== text) {
      const nodes = text.split(/(:)/).map(part => {
        if (part !== ':') return document.createTextNode(part);
        const node = document.createElement('span');
        node.className = 'overlay-preview-separator'; node.textContent = ':';
        return node;
      });
      clock.replaceChildren(...nodes);
    }
    clock.classList.toggle('blink-hidden', checked('clock_blink_separators') && elapsedMillis()%1000 >= 500);
    if (!show || !screen.clientHeight) return;
    const nativeLeft = Math.round(geometry.width*margins.left/100);
    const nativeRight = Math.round(geometry.width*margins.right/100);
    const nativeTop = Math.round(geometry.height*margins.top/100);
    const nativeBottom = Math.round(geometry.height*margins.bottom/100);
    const nativeHeight = Math.max(1,geometry.height-nativeTop-nativeBottom);
    const nativeWidth = Math.max(1,geometry.width-nativeLeft-nativeRight);
    const scale = screen.clientHeight / geometry.height;
    const requested = Math.trunc(Number(value('clock_font_size',26))) || 26;
    let size = Math.max(8, Math.min(Math.max(8,Math.min(512,Math.floor(nativeHeight/4))),requested));
    // Fit in native pixels before scaling the preview, just like the viewer.
    const stretch=Math.max(1,Math.min(4000,Math.round(100/geometry.pixel_aspect)))/100;
    const measure=()=>{context.font=`${size}px "EchoView Clock"`;return context.measureText(text);};
    const width=Math.round(measure().width*stretch);
    if (width>Math.max(1,nativeWidth-20)) size=Math.max(8,Math.trunc(size*Math.max(1,nativeWidth-20)/width));
    const metrics=measure();
    clock.style.fontSize = `${size*scale}px`;
    const lineHeight=Number.isFinite(metrics.fontBoundingBoxAscent+metrics.fontBoundingBoxDescent) ? Math.round(metrics.fontBoundingBoxAscent+metrics.fontBoundingBoxDescent)+2 : Math.round(size*1.1640625)+2;
    clock.style.lineHeight = `${lineHeight*scale}px`;
    const margin = Math.max(0,Math.min(10,Math.floor(nativeWidth/10),Math.floor(nativeHeight/10)));
    const mx = margin*geometry.pixel_aspect*scale, my = margin*scale;
    clock.style.width = `${Math.min(Math.max(1,nativeWidth-2*margin),Math.round(metrics.width*stretch)+2)*geometry.pixel_aspect*scale}px`;
    clock.style.overflow='hidden';
    const position = value('clock_position','bottom-center');
    clock.style.textAlign=position.includes('left')?'left':position.includes('right')?'right':'center';
    clock.style.left = position.includes('left') ? `${mx}px` : position.includes('right') ? 'auto' : '50%';
    clock.style.right = position.includes('right') ? `${mx}px` : 'auto';
    clock.style.top = position.includes('top') ? `${my}px` : position.includes('bottom') ? 'auto' : '50%';
    clock.style.bottom = position.includes('bottom') ? `${my}px` : 'auto';
    const x = position.includes('left') || position.includes('right') ? '0' : '-50%';
    const y = position.includes('top') || position.includes('bottom') ? '0' : '-50%';
    clock.style.transform = `translate(${x},${y})`;
  }
  const renderAll = () => previews.forEach(render);
  // Font arrival changes measurements; never retain a fallback-font layout.
  document.fonts.load('26px "EchoView Clock"').then(renderAll).catch(() => {});
  form.addEventListener('input',() => { renderAll(); schedule(); });
  form.addEventListener('change',() => { renderAll(); schedule(); });
  for (const preview of previews) new ResizeObserver(() => render(preview)).observe(preview);
  const frames = new Map(previews.map(preview => [preview, {visible: false, timer: null, request: null, url: null}]));
  async function refreshFrame(preview, manual=false) {
    const state = frames.get(preview);
    clearTimeout(state.timer); state.timer = null;
    if (document.hidden || state.request || (!manual && !state.visible)) return;
    const live = preview.querySelector('[data-preview-live]').checked;
    if (!manual && !live && state.url) return;
    const controller = new AbortController(); state.request = controller;
    const timeout = setTimeout(() => controller.abort(), 5000);
    const status = preview.querySelector('[data-preview-status]');
    try {
      const response = await fetch(preview.dataset.frameUrl, {cache:'no-store', signal:controller.signal});
      if (!response.ok || !response.headers.get('Content-Type')?.includes('image/jpeg')) throw new Error('Unavailable');
      const url = URL.createObjectURL(await response.blob());
      const decoded = new Image(); decoded.src = url;
      try { await decoded.decode(); } catch (error) { URL.revokeObjectURL(url); throw error; }
      if (controller.signal.aborted || document.hidden) { URL.revokeObjectURL(url); return; }
      const image = preview.querySelector('[data-overlay-frame]'), previous = state.url;
      image.src = url; image.hidden = false; state.url = url;
      if (previous) URL.revokeObjectURL(previous);
      status.textContent = live ? 'Current frame' : 'Paused preview';
    } catch (_) {
      if (controller.signal.aborted) return;
      status.textContent = state.url ? 'Preview delayed' : 'Preview unavailable';
    } finally {
      clearTimeout(timeout); state.request = null;
      if (!document.hidden && state.visible && preview.querySelector('[data-preview-live]').checked) {
        state.timer = setTimeout(() => refreshFrame(preview), 2000);
      }
    }
  }
  function stopFrame(preview) {
    const state = frames.get(preview);
    clearTimeout(state.timer); state.timer = null; state.request?.abort();
  }
  const observer = new IntersectionObserver(entries => entries.forEach(entry => {
    const state = frames.get(entry.target); state.visible = entry.isIntersecting;
    if (state.visible) refreshFrame(entry.target); else stopFrame(entry.target);
  }));
  for (const preview of previews) {
    observer.observe(preview);
    preview.querySelector('[data-preview-refresh]').addEventListener('click', () => refreshFrame(preview,true));
    preview.querySelector('[data-preview-live]').addEventListener('change', event => {
      if (event.target.checked) refreshFrame(preview);
      else { stopFrame(preview); preview.querySelector('[data-preview-status]').textContent = 'Paused preview'; }
    });
  }
  window.addEventListener('pagehide', () => {
    for (const [preview,state] of frames) { stopFrame(preview); if (state.url) URL.revokeObjectURL(state.url); }
  });
  let timer;
  function schedule() {
    clearInterval(timer);
    if (document.hidden) return;
    const blink = previews.some(preview => form.elements.namedItem(preview.dataset.display+'_clock_enabled')?.checked && form.elements.namedItem(preview.dataset.display+'_clock_blink_separators')?.checked);
    timer=setInterval(renderAll,blink ? 500 : 1000);
  }
  function visibility() {
    if (!document.hidden) renderAll();
    for (const preview of previews) {
      if (document.hidden) stopFrame(preview); else refreshFrame(preview);
    }
    schedule();
  }
  document.addEventListener('visibilitychange',visibility);
  window.addEventListener('pageshow',visibility);
  visibility();
});
