// Read the viewer's local snapshot. This endpoint never calls Spotify.
document.addEventListener('DOMContentLoaded', () => {
  const panel = document.querySelector('[data-now-playing]');
  if (!panel) return;
  const field = name => panel.querySelector(`[data-np-${name}]`);
  const meter = panel.querySelector('[role="progressbar"]');
  const messages = {
    inactive: ['Not on display', 'Choose Spotify on a display', 'Use Displays to select Spotify as a playback mode.'],
    waiting: ['Waiting', 'Waiting for the display', 'Playback will appear when the viewer publishes its first update.'],
    stale: ['Update delayed', 'Waiting for fresh playback data', 'The display has not sent a recent update.'],
    unavailable: ['Idle', 'Nothing is playing', 'Start listening in Spotify and the display will follow.'],
    authorization_required: ['Reconnect', 'Spotify needs authorization', 'Use the connection settings below to reconnect.'],
    access_denied: ['Access denied', 'Spotify access is unavailable', 'Check the app’s allowed users and Premium requirements.'],
    rate_limited: ['Waiting', 'Spotify is limiting requests', 'EchoView will retry after Spotify’s waiting period.'],
    quota_exceeded: ['Waiting', 'Spotify quota reached', 'EchoView has paused requests and will retry later.'],
    offline: ['Offline', 'Spotify is temporarily unavailable', 'EchoView will reconnect automatically.'],
  };
  let timer, animation, request, sample = null, received = 0;
  const time = milliseconds => {
    const seconds = Math.max(0, Math.floor(milliseconds / 1000));
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
  };
  function progress() {
    const duration = Number(sample?.duration_ms) || 0;
    const elapsed = (Number(sample?.progress_ms) || 0) + (sample?.status === 'playing' ? performance.now() - received : 0);
    const position = Math.min(duration, Math.max(0, elapsed));
    const percent = duration > 0 ? position / duration * 100 : 0;
    field('fill').style.transform = `scaleX(${percent / 100})`;
    meter.setAttribute('aria-valuenow', String(Math.round(percent)));
    field('elapsed').textContent = time(position);
    field('duration').textContent = time(duration);
  }
  function render(data) {
    sample = data; received = performance.now();
    const hasTrack = ['playing', 'paused'].includes(data.status);
    const message = messages[data.status] || messages.waiting;
    field('status').textContent = hasTrack ? (data.status === 'playing' ? 'Playing' : 'Paused') : message[0];
    field('status').classList.toggle('active', data.status === 'playing');
    field('title').textContent = hasTrack ? data.song || 'Untitled track' : message[1];
    field('artist').textContent = hasTrack ? data.artist || '' : '';
    field('album').textContent = hasTrack ? data.album || '' : '';
    field('device').textContent = hasTrack && data.device_name ? `Listening on ${data.device_name}` : 'Spotify';
    field('note').textContent = hasTrack ? [data.shuffle ? 'Shuffle on' : '', data.repeat === 'track' ? 'Repeating track' : data.repeat === 'context' ? 'Repeat on' : ''].filter(Boolean).join(' · ') : message[2];
    const art = field('art');
    if (hasTrack && data.artwork) {
      if (art.getAttribute('src') !== data.artwork) art.src = data.artwork;
      art.hidden = false;
    } else { art.hidden = true; art.removeAttribute('src'); }
    progress();
  }
  field('art').addEventListener('error', () => { field('art').hidden = true; });
  async function refresh() {
    if (document.hidden) return;
    const controller = new AbortController();
    request = controller;
    const timeout = setTimeout(() => { controller.abort(); render({status: 'stale'}); }, 10000);
    try {
      const response = await fetch(panel.dataset.url, {cache: 'no-store', signal: controller.signal});
      if (!response.ok) throw new Error('Unavailable');
      render(await response.json());
    } catch (error) {
      if (error.name !== 'AbortError') render({status: 'stale'});
    } finally {
      clearTimeout(timeout);
      if (request === controller) {
        request = null;
        if (!document.hidden) timer = setTimeout(refresh, 5000);
      }
    }
  }
  function visibility() {
    clearTimeout(timer); clearInterval(animation); request?.abort(); request = null;
    if (!document.hidden) { refresh(); animation = setInterval(progress, 200); }
  }
  document.addEventListener('visibilitychange', visibility);
  visibility();
});
