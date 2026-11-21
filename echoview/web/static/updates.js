/* Update requests are sent once. Polling may retry; installation never does. */
(() => {
  const actions = document.querySelector('.update-actions');
  if (!actions) return;
  const forms = [...actions.querySelectorAll('form')];
  const panel = document.getElementById('update-progress');
  const stage = document.getElementById('update-stage');
  const detail = document.getElementById('update-detail');
  const elapsed = document.getElementById('update-elapsed');
  const check = document.getElementById('check-update');
  const release = document.getElementById('release-status');
  const changes = document.getElementById('release-changes');
  const branch = document.getElementById('update-branch');
  let busy = false;
  let started = 0;
  let timer;
  let disconnectedAt = 0;

  function controls() {
    const unsaved = branch.value !== actions.dataset.savedBranch;
    forms.forEach(form => { form.querySelector('button').disabled = busy || unsaved; });
    check.disabled = busy || unsaved;
    if (unsaved) release.textContent = 'Save your branch selection before checking or installing.';
  }
  branch.addEventListener('change', controls);

  async function json(url, options = {}) {
    const response = await fetch(url, {...options, cache: 'no-store',
      headers: {Accept: 'application/json'}, signal: AbortSignal.timeout(35000)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'The request could not be completed.');
    return data;
  }

  function show(data) {
    if (data.status === 'idle') {
      busy = false;
      controls();
      return;
    }
    panel.hidden = false;
    stage.textContent = data.message;
    started = data.started_at || started;
    busy = ['running', 'awaiting_restart'].includes(data.status);
    panel.setAttribute('aria-busy', String(busy));
    detail.textContent = data.status === 'completed'
      ? `EchoView ${data.version} is online. ${data.branch} update finished.`
      : data.status === 'failed' || data.status === 'interrupted'
        ? 'No automatic retry was made. Code or dependencies may have changed; use the recovery guide before retrying.'
        : `Updating from ${data.branch}. You can leave this page and return to check progress.`;
    if (data.status === 'awaiting_restart' && Date.now() / 1000 - data.updated_at > 120) {
      detail.textContent = 'The controller restart is taking longer than expected. Check the service journal; installation finished, but controller return has not been confirmed.';
    }
    controls();
    if (!busy) elapsed.textContent = '';
  }

  async function poll() {
    clearTimeout(timer);
    try {
      const data = await json('/update_status');
      disconnectedAt = 0;
      show(data);
    } catch (_) {
      if (busy) {
        disconnectedAt ||= Date.now();
        stage.textContent = 'Connection lost. Checking for the device to return…';
        detail.textContent = 'A restart can temporarily disconnect this page. Do not start another update.';
      } else {
        panel.hidden = false;
        stage.textContent = 'Update status is unavailable.';
        detail.textContent = 'Reload this page to check the last attempt before starting an update.';
      }
    }
    if (busy && disconnectedAt && Date.now() - disconnectedAt > 5 * 60 * 1000) {
      stage.textContent = 'The device has not reconnected yet.';
      detail.textContent = 'Check power and network access, then reload this page. The update outcome is unknown.';
      return;
    }
    if (busy) timer = setTimeout(poll, 2500);
  }

  setInterval(() => {
    if (busy && started) {
      const seconds = Math.max(0, Math.floor(Date.now() / 1000 - started));
      elapsed.textContent = `Elapsed: ${Math.floor(seconds / 60)}m ${seconds % 60}s. Dependency installation may take several minutes.`;
    }
  }, 1000);

  check.addEventListener('click', async () => {
    check.disabled = true;
    release.textContent = `Checking ${actions.dataset.savedBranch}…`;
    changes.replaceChildren();
    try {
      const data = await json('/check_update', {method: 'POST'});
      release.textContent = data.available
        ? `Available: ${data.version} on ${data.branch} (${data.target_revision}). Installed revision: ${data.current_revision}.`
        : `You are up to date on ${data.branch}: ${data.version}. You can reinstall if needed.`;
      changes.replaceChildren(...data.changes.map(message => {
        const item = document.createElement('li');
        item.textContent = message;
        return item;
      }));
    } catch (error) { release.textContent = error.message; }
    finally { controls(); }
  });

  forms.forEach(form => form.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || branch.value !== actions.dataset.savedBranch) return;
    busy = true;
    started = Date.now() / 1000;
    panel.hidden = false;
    stage.textContent = 'Starting update…';
    controls();
    try {
      show(await json(form.action, {method: 'POST'}));
    } catch (error) {
      stage.textContent = error.message;
      detail.textContent = 'Checking whether the device accepted the update. The request will not be sent again.';
    }
    await poll();
  }));
  controls();
  poll();
})();
