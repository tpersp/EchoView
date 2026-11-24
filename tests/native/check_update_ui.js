/* Run with: node --test tests/native/check_update_ui.js */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function fixture(initial = {status: 'idle'}) {
  const element = () => ({textContent: '', hidden: true, disabled: false,
    listeners: {}, children: [], dataset: {},
    addEventListener(event, callback) { this.listeners[event] = callback; },
    setAttribute() {}, replaceChildren(...items) { this.children = items; }});
  const elements = Object.fromEntries(['update-progress', 'update-stage', 'update-detail',
    'update-elapsed', 'check-update', 'release-status', 'release-changes', 'update-branch']
    .map(id => [id, element()]));
  elements['update-branch'].value = 'main';
  const forms = ['/update_app', '/full_update'].map(action => {
    const form = element();
    form.action = action;
    form.button = element();
    form.querySelector = () => form.button;
    return form;
  });
  const actions = {dataset: {savedBranch: 'main'}, querySelectorAll: () => forms};
  const timers = new Map();
  const calls = [];
  let timerID = 0;
  const data = {state: initial, startFails: false};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,
    '../../echoview/web/static/updates.js'), 'utf8'), {
    document: {querySelector: () => actions, getElementById: id => elements[id],
      createElement: element},
    AbortSignal, Date,
    setTimeout: callback => { timers.set(++timerID, callback); return timerID; },
    clearTimeout: id => timers.delete(id), setInterval: () => 1,
    fetch: async (url, options) => {
      calls.push({url, options});
      if (url === '/update_app' || url === '/full_update') {
        data.state = {status: 'running', message: 'Installing dependencies', branch: 'main', started_at: Date.now() / 1000};
        if (data.startFails) throw new Error('Lost response');
      }
      return {ok: true, json: async () => url === '/check_update'
        ? {available: true, version: '1.20.0', branch: 'main', target_revision: 'new',
          current_revision: 'old', changes: ['<img src=x onerror=alert(1)>']}
        : {...data.state}};
    },
  });
  return {elements, forms, calls, data,
    settle: async () => { for (let i = 0; i < 5; i++) await new Promise(setImmediate); },
    tick: async () => {
      const [id, callback] = timers.entries().next().value;
      timers.delete(id);
      await callback();
    }};
}

test('preview renders commit subjects as text and unsaved branch disables installation', async () => {
  const {elements, forms, settle} = fixture();
  await settle();
  await elements['check-update'].listeners.click();
  assert.match(elements['release-status'].textContent, /1.20.0/);
  assert.equal(elements['release-changes'].children[0].textContent, '<img src=x onerror=alert(1)>');
  elements['update-branch'].value = 'dev';
  elements['update-branch'].listeners.change();
  assert.ok(forms.every(form => form.button.disabled));
  assert.ok(elements['check-update'].disabled);
});

test('one installation request, live stages, and confirmed controller return', async () => {
  const {elements, forms, calls, data, settle, tick} = fixture();
  await settle();
  await forms[0].listeners.submit({preventDefault() {}});
  assert.equal(elements['update-stage'].textContent, 'Installing dependencies');
  assert.ok(forms.every(form => form.button.disabled));
  await forms[0].listeners.submit({preventDefault() {}});
  assert.equal(calls.filter(call => call.url === '/update_app').length, 1);
  data.state = {...data.state, status: 'awaiting_restart', message: 'Waiting for restart', updated_at: Date.now() / 1000};
  await tick();
  assert.ok(forms[0].button.disabled);
  data.state = {...data.state, status: 'completed', version: '1.20.0', message: 'Controller returned'};
  await tick();
  assert.match(elements['update-detail'].textContent, /1.20.0 is online/);
  assert.equal(forms[0].button.disabled, false);
});

test('refresh resumes a running attempt and a lost start response never resubmits', async () => {
  const resumed = fixture({status: 'running', branch: 'main', message: 'Still installing'});
  await resumed.settle();
  assert.equal(resumed.elements['update-stage'].textContent, 'Still installing');
  assert.ok(resumed.forms[0].button.disabled);
  const lost = fixture();
  await lost.settle();
  lost.data.startFails = true;
  await lost.forms[0].listeners.submit({preventDefault() {}});
  await lost.tick();
  assert.equal(lost.calls.filter(call => call.url === '/update_app').length, 1);
  assert.equal(lost.elements['update-stage'].textContent, 'Installing dependencies');
});

test('interrupted attempts show recovery guidance and allow a deliberate retry', async () => {
  const {elements, forms, settle} = fixture({status: 'interrupted', branch: 'main', message: 'Interrupted'});
  await settle();
  assert.equal(elements['update-stage'].textContent, 'Interrupted');
  assert.match(elements['update-detail'].textContent, /No automatic retry/);
  assert.equal(forms[0].button.disabled, false);
});
