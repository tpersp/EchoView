// Browse only the folder and page the user is interacting with.
document.addEventListener('DOMContentLoaded', () => {
  const manager = document.getElementById('file-manager');
  if (manager) initMediaFolders(manager);
  document.querySelectorAll('.specific-picker').forEach(initSpecificPicker);
  const displayForm = document.getElementById('display-settings-form');
  if (displayForm) {
    const status = document.getElementById('display-save-status');
    displayForm.addEventListener('change', event => {
      if (!event.target.name) return; // Searching the picker does not change playback settings.
      status.textContent = 'Unsaved changes';
      displayForm.querySelector('.save-bar')?.classList.add('has-changes');
      document.querySelector('#save-preset-form button').disabled = true;
    });
    displayForm.addEventListener('submit', () => {
      status.textContent = 'Applying settings…';
      const button = document.getElementById('display-save-button');
      button.disabled = true;
      button.textContent = 'Applying…';
    });
  }
});

function initMediaFolders(manager) {
  const folders = Array.from(manager.querySelectorAll('.media-folder'));
  const sort = document.getElementById('sort_select');
  let savedFolder;
  try { savedFolder = sessionStorage.getItem('echoview-media-folder'); } catch (_) {}
  function remember(folder) {
    const url = new URL(location.href);
    url.searchParams.set('sort', sort.value);
    url.searchParams.set('folder', folder.dataset.folderName);
    history.replaceState(null, '', url);
  }

  async function load(folder, page = 1) {
    const content = folder.querySelector('.folder-content');
    if (folder.request) folder.request.abort();
    const controller = new AbortController();
    folder.request = controller;
    const url = new URL(content.dataset.url, location.href);
    url.searchParams.set('sort', sort.value);
    url.searchParams.set('page', page);
    url.searchParams.set('q', folder.dataset.query || '');
    content.setAttribute('aria-busy', 'true');
    content.textContent = 'Loading files…';
    try {
      const response = await fetch(url, {signal: controller.signal});
      if (!response.ok) throw new Error('Cannot load this folder. Check the media connection and retry.');
      const html = await response.text();
      if (controller.signal.aborted) return;
      content.innerHTML = html;
      restorePlayTargets(content);
    } catch (error) {
      if (controller.signal.aborted) return;
      content.textContent = error.message + ' ';
      const retry = document.createElement('button');
      retry.type = 'button';
      retry.textContent = 'Retry';
      retry.addEventListener('click', () => load(folder, page));
      content.append(retry);
    } finally {
      if (folder.request === controller) {
        folder.request = null;
        content.removeAttribute('aria-busy');
      }
    }
  }

  folders.forEach(folder => {
    folder.addEventListener('toggle', () => {
      if (folder.open) {
        folders.forEach(other => { if (other !== folder) other.open = false; });
        try { sessionStorage.setItem('echoview-media-folder', folder.dataset.folderName); } catch (_) {}
        remember(folder);
        if (!folder.request) load(folder);
      } else {
        if (folder.request) folder.request.abort();
        folder.request = null;
        // Detaching previews stops videos and releases their network/decoder resources.
        folder.querySelectorAll('video').forEach(video => { video.pause(); video.removeAttribute('src'); video.load(); });
        folder.querySelector('.folder-content').replaceChildren();
        folder.querySelector('.folder-content').removeAttribute('aria-busy');
      }
    });
    folder.addEventListener('submit', event => {
      if (!event.target.matches('[data-folder-search]')) return;
      event.preventDefault();
      folder.dataset.query = new FormData(event.target).get('q');
      load(folder);
    });
    folder.addEventListener('click', event => {
      const button = event.target.closest('[data-media-page]');
      if (button) load(folder, Number(button.dataset.mediaPage));
    });
  });
  sort.addEventListener('change', () => folders.filter(folder => folder.open).forEach(folder => {
    remember(folder);
    load(folder);
  }));
  document.getElementById('media-sort-form').addEventListener('submit', event => event.preventDefault());
  document.getElementById('folder-search').addEventListener('input', event => {
    const query = event.target.value.toLocaleLowerCase();
    let visible = 0;
    folders.forEach(folder => {
      folder.hidden = !folder.dataset.folderName.toLocaleLowerCase().includes(query);
      if (folder.hidden) folder.open = false;
      else visible++;
    });
    document.getElementById('folder-search-status').textContent = `${visible} folders`;
  });
  if (!folders.some(folder => folder.open)) {
    const remembered = folders.find(folder => folder.dataset.folderName === savedFolder);
    if (remembered) remembered.open = true;
  } else {
    folders.filter(folder => folder.open).forEach(folder => load(folder));
  }
}

function restorePlayTargets(root) {
  root.querySelectorAll('.media-play button').forEach(button => { button.disabled = playRequestPending; });
  let target;
  try { target = sessionStorage.getItem('echoview-play-display'); } catch (_) {}
  if (!target) return;
  root.querySelectorAll('.media-play select[name="display"]').forEach(select => {
    if (Array.from(select.options).some(option => option.value === target)) select.value = target;
  });
}

let playRequestPending = false;
document.addEventListener('change', event => {
  if (!event.target.matches('.media-play select[name="display"]')) return;
  try { sessionStorage.setItem('echoview-play-display', event.target.value); } catch (_) {}
  restorePlayTargets(document);
});

document.addEventListener('submit', async event => {
  const form = event.target;
  if (!form.matches('[data-play-media]')) return;
  event.preventDefault();
  if (playRequestPending) return;
  const status = form.querySelector('.play-status');
  const body = new FormData(form);
  const showStatus = message => {
    status.textContent = message;
    const globalStatus = document.getElementById('media-play-status');
    if (globalStatus) globalStatus.textContent = `${body.get('display')}: ${message}`;
  };
  playRequestPending = true;
  document.querySelectorAll('.media-play button').forEach(button => { button.disabled = true; });
  showStatus('Applying to display…');
  try {
    const response = await fetch(form.action, {
      method: 'POST', body, headers: {'Accept': 'application/json'},
      signal: AbortSignal.timeout(25000)
    });
    const result = await response.json();
    showStatus(result.message);
  } catch (error) {
    showStatus('Could not confirm the request. Check Displays before retrying.');
  } finally {
    playRequestPending = false;
    document.querySelectorAll('.media-play button').forEach(button => { button.disabled = false; });
  }
});

function initSpecificPicker(picker) {
  const display = picker.dataset.display;
  const form = picker.closest('form');
  const video = picker.dataset.kind === 'video';
  const kind = video ? 'videos' : 'images';
  const previews = video ? createVideoPreviewManager(picker) : null;
  const section = document.getElementById(display + (video ? '_specific_video_section' : '_specific_image_section'));
  const selection = video ? document.getElementById(display + '_video_selection') : null;
  const category = form.elements.namedItem(display + (video ? '_video_category' : '_image_category'));
  const aspect = form.elements.namedItem(display + '_aspect_filter');
  const value = document.getElementById(display + (video ? '_video_value' : '_specific_value'));
  const results = picker.querySelector('.specific-results');
  const more = picker.querySelector('.specific-more');
  const search = picker.querySelector('.specific-search');
  let request;
  let loaded = false;
  let nextPage = 1;

  async function load(reset = true) {
    if (!reset && request) return;
    if (request) request.abort();
    const controller = new AbortController();
    request = controller;
    if (reset) { previews?.clear(); nextPage = 1; results.textContent = `Loading ${kind}…`; }
    more.hidden = true;
    const url = new URL(picker.dataset.url, location.href);
    url.search = new URLSearchParams({folder: category.value, aspect: video ? 'any' : aspect.value, q: search.value, page: nextPage});
    picker.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch(url, {signal: controller.signal});
      if (!response.ok) throw new Error(`Cannot load ${kind}. Check the media connection and retry.`);
      const data = await response.json();
      if (controller.signal.aborted) return;
      if (reset) results.replaceChildren();
      data.files.forEach(name => {
        const label = document.createElement('label');
        label.className = 'thumb-label';
        const image = video ? null : document.createElement('img');
        if (image) {
          const path = [category.value, name].filter(Boolean).map(encodeURIComponent).join('/');
          image.src = '/thumb/' + path + '?size=80';
          image.loading = 'lazy';
          image.decoding = 'async';
          image.width = 80; image.height = 80; image.alt = name;
        }
        const radio = document.createElement('input');
        radio.type = 'radio'; radio.name = display + (video ? '_video_picker' : '_picker'); radio.value = name;
        radio.checked = value.value === name;
        radio.addEventListener('change', () => {
          value.value = name;
          document.getElementById(display + (video ? '_video_selected' : '_specific_selected')).textContent = name;
          if (video) document.getElementById(display + '_video_folder').value = category.value;
        });
        if (image) label.append(image, document.createElement('br'));
        label.append(radio, document.createTextNode(' ' + name));
        results.append(label);
        if (previews) previews.add(label, name, category.value);
      });
      if (!data.total) results.textContent = `No matching ${kind} in this folder.`;
      nextPage = data.page + 1;
      more.textContent = 'Load more';
      more.hidden = data.page >= data.pages;
      loaded = true;
    } catch (error) {
      if (controller.signal.aborted) return;
      if (reset) results.textContent = error.message;
      more.textContent = 'Retry';
      more.hidden = false;
    } finally {
      if (request === controller) {
        request = null;
        picker.removeAttribute('aria-busy');
      }
    }
  }
  more.addEventListener('click', () => load(nextPage === 1));
  picker.querySelector('.specific-search-button').addEventListener('click', () => load());
  search.addEventListener('keydown', event => {
    if (event.key === 'Enter') { event.preventDefault(); load(); }
  });
  const check = () => {
    if (document.hidden || section.style.display === 'none' || (video && (section.hidden || form.elements.namedItem(display + '_mode').value !== 'videos'))) {
      previews?.pause();
      if (request) { request.abort(); request = null; }
    } else {
      previews?.resume();
      if (!loaded && !request) load();
    }
  };
  (video ? [category] : [category, aspect]).forEach(control => control.addEventListener('change', () => {
    if (video) {
      value.value = '';
      document.getElementById(display + '_video_selected').textContent = 'None';
    }
    previews?.clear();
    loaded = false;
    if (request) { request.abort(); request = null; }
    check();
  }));
  [form.elements.namedItem(display + '_mode'), form.elements.namedItem(display + '_fallback_mode')]
    .filter(Boolean).forEach(control => control.addEventListener('change', check));
  if (video) {
    selection.addEventListener('change', () => {
      section.hidden = selection.value !== 'specific';
      document.getElementById(display + '_video_order').hidden = !section.hidden;
      if (section.hidden) {
        value.value = '';
        results.querySelectorAll('input[type=radio]').forEach(input => { input.checked = false; });
        document.getElementById(display + '_video_selected').textContent = 'None';
      }
      check();
    });
  }
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) previews?.pause(); else check();
  });
  window.addEventListener('pagehide', event => { if (event.persisted) previews?.pause(); else previews?.clear(); });
  window.addEventListener('pageshow', check);
  check();
}

// Cached JPEGs, not video elements: one request at a time and motion only on demand.
function createVideoPreviewManager(picker) {
  const cards = new Set();
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  reducedMotion.addEventListener('change', () => { if (reducedMotion.matches) cards.forEach(stop); });
  let jobs = [], active = 0, paused = false;
  const observer = new IntersectionObserver(entries => entries.forEach(entry => {
    const card = entry.target.previewCard;
    card.visible = entry.isIntersecting;
    if (card.visible && !paused) enqueue(card, false);
    if (!card.visible) stop(card);
  }), {rootMargin: '80px'});
  function stop(card) {
    card.hover = false;
    clearInterval(card.timer); clearTimeout(card.delay);
    card.timer = null;
    if (card.poster) card.image.src = card.poster; else card.image.removeAttribute('src');
    card.image.classList.remove('video-sprite');
    card.image.style.transform = '';
  }
  function animate(card) {
    if (!card.hover || paused || !card.motion || card.timer) return;
    card.image.src = card.motion;
    card.image.classList.add('video-sprite');
    let frame = 0;
    const tick = () => { card.image.style.transform = `translateX(-${frame * 25}%)`; frame = (frame + 1) % 4; };
    tick(); card.timer = setInterval(tick, 650);
  }
  function enqueue(card, motion) {
    if (paused || !card.label.isConnected || !card.visible || (motion ? card.motion : card.poster)) return;
    if (card.requests.has(motion) || jobs.some(job => job.card === card && job.motion === motion)) return;
    if (motion) jobs.unshift({card, motion}); else jobs.push({card, motion});
    drain();
  }
  function drain() {
    if (paused) return;
    // Concurrent cache checks do not create parallel server-side decoders.
    while (active < 4 && jobs.length) {
      const job = jobs.shift();
      const {card, motion} = job;
      if (!card.label.isConnected || !card.visible || (motion && !card.hover) || card.requests.has(motion) || (motion ? card.motion : card.poster)) continue;
      active++;
      loadPreview(job).finally(() => { active--; drain(); });
    }
  }
  async function loadPreview({card, motion}) {
    const abort = new AbortController(); card.requests.set(motion, abort);
    const url = new URL('/media/video-preview', location.href);
    url.search = new URLSearchParams({folder: card.folder, file: card.name, motion: motion ? '1' : '0'});
    try {
      for (let attempt = 0; attempt < 120; attempt++) {
        if (paused || !card.label.isConnected || !card.visible || (motion && !card.hover)) break;
        const response = await fetch(url, {signal: abort.signal});
        if (response.status === 202) {
          if (attempt === 119) throw new Error('Preview unavailable');
          await new Promise(resolve => setTimeout(resolve, 350)); continue;
        }
        if (!response.ok) throw new Error('Preview unavailable');
        const blob = await response.blob();
        if (abort.signal.aborted || !card.label.isConnected) break;
        const objectURL = URL.createObjectURL(blob);
        if (motion) { card.motion = objectURL; animate(card); }
        else { card.poster = objectURL; if (!card.timer) card.image.src = objectURL; card.label.classList.add('has-video-poster'); }
        break;
      }
    } catch (error) {
      if (error.name !== 'AbortError' && !card.poster) card.placeholder.textContent = 'Preview unavailable';
    } finally { if (card.requests.get(motion) === abort) card.requests.delete(motion); }
  }
  return {
    add(label, name, folder) {
      const frame = document.createElement('span'); frame.className = 'video-preview-frame';
      const image = document.createElement('img'); image.alt = ''; image.decoding = 'async';
      const placeholder = document.createElement('span'); placeholder.className = 'video-preview-placeholder'; placeholder.textContent = 'Loading preview…';
      frame.append(image, placeholder); label.prepend(frame);
      const card = {label, name, folder, image, placeholder, visible: false, requests: new Map()};
      label.previewCard = card; cards.add(card); observer.observe(label);
      const start = () => {
        if (reducedMotion.matches) return;
        card.hover = true;
        card.delay = setTimeout(() => { if (card.motion) animate(card); else enqueue(card, true); }, 250);
      };
      label.addEventListener('mouseenter', start);
      label.addEventListener('mouseleave', () => stop(card));
      label.addEventListener('focusin', start);
      label.addEventListener('focusout', () => stop(card));
    },
    pause() { paused = true; jobs = []; cards.forEach(card => { stop(card); card.requests.forEach(abort => abort.abort()); }); },
    resume() { paused = false; cards.forEach(card => { if (card.visible) enqueue(card, false); }); drain(); },
    clear() {
      jobs = [];
      cards.forEach(card => {
        observer.unobserve(card.label); stop(card); card.requests.forEach(abort => abort.abort());
        if (card.poster) URL.revokeObjectURL(card.poster);
        if (card.motion) URL.revokeObjectURL(card.motion);
      });
      cards.clear();
    }
  };
}
