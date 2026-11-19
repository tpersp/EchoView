// Clock previews use device time embedded in the page. No media or API requests.
document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('overlay-settings-form');
  const previews = [...document.querySelectorAll('[data-overlay-preview]')];
  if (!form || !previews.length) return;
  const sampled = performance.now();
  const startSeconds = Number(form.dataset.clockSeconds) || 0;
  function clockText() {
    const seconds = (startSeconds + Math.floor((performance.now()-sampled)/1000)) % 86400;
    return [Math.floor(seconds/3600), Math.floor(seconds/60)%60, seconds%60].map(value => String(value).padStart(2,'0')).join(':');
  }
  function render(preview) {
    const prefix = preview.dataset.display + '_';
    const value = (key,fallback) => form.elements.namedItem(prefix+key)?.value ?? fallback;
    const checked = key => form.elements.namedItem(prefix+key)?.checked ?? false;
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
    clock.textContent = clockText();
    if (!show || !screen.clientHeight) return;
    const nativeHeight = geometry.height * (1-(margins.top+margins.bottom)/100);
    const nativeWidth = geometry.width * (1-(margins.left+margins.right)/100);
    const scale = screen.clientHeight / geometry.height;
    const requested = Number(value('clock_font_size',26)) || 26;
    const size = Math.max(8, Math.min(512, Math.floor(nativeHeight/4), requested));
    clock.style.fontSize = `${size*scale}px`;
    const margin = Math.max(0, Math.min(10, Math.floor(nativeWidth/4), Math.floor(nativeHeight/4)));
    const mx = margin*geometry.pixel_aspect*scale, my = margin*scale;
    const available = Math.max(1,safe.clientWidth-2*mx);
    if (clock.getBoundingClientRect().width>available) {
      clock.style.fontSize = `${Math.max(8*scale,size*scale*available/clock.getBoundingClientRect().width)}px`;
    }
    const position = value('clock_position','bottom-center');
    clock.style.left = position.includes('left') ? `${mx}px` : position.includes('right') ? 'auto' : '50%';
    clock.style.right = position.includes('right') ? `${mx}px` : 'auto';
    clock.style.top = position.includes('top') ? `${my}px` : position.includes('bottom') ? 'auto' : '50%';
    clock.style.bottom = position.includes('bottom') ? `${my}px` : 'auto';
    const x = position.includes('left') || position.includes('right') ? '0' : '-50%';
    const y = position.includes('top') || position.includes('bottom') ? '0' : '-50%';
    clock.style.transform = `translate(${x},${y})`;
  }
  const renderAll = () => previews.forEach(render);
  form.addEventListener('input',renderAll);
  form.addEventListener('change',renderAll);
  for (const preview of previews) new ResizeObserver(() => render(preview)).observe(preview);
  let timer;
  function visibility() {
    clearInterval(timer);
    if (!document.hidden) { renderAll(); timer=setInterval(renderAll,1000); }
  }
  document.addEventListener('visibilitychange',visibility);
  visibility();
});
