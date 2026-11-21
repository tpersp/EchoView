// Layout previews are browser-only and read the viewer's existing local snapshot.
document.addEventListener('DOMContentLoaded', () => {
  const previews = [...document.querySelectorAll('.spotify-preview')];
  if (!previews.length) return;
  let sample = null, timer, controller;
  const example = {song: 'Song title', artist: 'Artist name', album: 'Album name', device_name: 'Living room', progress_ms: 60000, duration_ms: 180000};
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
    for (const name of ['song','artist','album','device']) {
      const node = preview.querySelector(`[data-preview-${name}]`);
      const text = name === 'device' ? (data.device_name ? `Playing on ${data.device_name}` : '') : data[name] || '';
      node.textContent = enabled('spotify_show_' + name, name !== 'device') ? text : '';
      node.hidden = !node.textContent;
    }
    const image = preview.querySelector('img');
    if (data.artwork) {
      if (image.getAttribute('src') !== data.artwork) image.src = data.artwork;
      image.hidden = false;
    } else { image.hidden = true; image.removeAttribute('src'); }
    const scale = Math.max(.1, screen.clientHeight / height);
    screen.style.setProperty('--preview-font', `${Math.max(5, (Number(value('spotify_font_size',18)) || 18)*scale)}px`);
    screen.style.setProperty('--preview-color', enabled('spotify_negative_font',true) ? '#edf2f7' : value('spotify_font_color','#ffffff'));
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
    preview.querySelector('[data-preview-note]').textContent = data === example ? 'Example track' : 'Now playing';
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
