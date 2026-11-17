// Daily schedules use the device clock, including when the browser is elsewhere.
document.addEventListener('DOMContentLoaded', () => {
  const roots = Array.from(document.querySelectorAll('.schedule-editor'));
  if (!roots.length) return;
  const clock = {value: JSON.parse(roots[0].dataset.clock), received: Date.now()};
  const editors = roots.map(root => new ScheduleEditor(root, clock));
  let pending = false;
  let lastAttempt = 0;
  async function syncClock() {
    if (pending || document.hidden || Date.now() - lastAttempt < 30000 || !editors.some(editor => editor.active())) return;
    pending = true;
    lastAttempt = Date.now();
    try {
      const response = await fetch(roots[0].dataset.clockUrl, {cache: 'no-store', signal: AbortSignal.timeout(5000)});
      if (response.ok) { clock.value = await response.json(); clock.received = Date.now(); }
    } catch (_) { /* Keep the last device clock estimate and retry on the next tick. */ }
    finally { pending = false; }
  }
  setInterval(() => {
    if (document.hidden) return;
    editors.filter(editor => editor.active()).forEach(editor => editor.tick());
    if (Date.now() - clock.received > 60000) syncClock();
  }, 1000);
  document.addEventListener('visibilitychange', syncClock);
  editors.forEach(editor => editor.mode.addEventListener('change', syncClock));
});

class ScheduleEditor {
  constructor(root, clock) {
    this.root = root;
    this.clock = clock;
    this.mode = root.closest('form').elements.namedItem(root.dataset.display + '_mode');
    this.json = root.querySelector('input[type="hidden"]');
    this.error = root.querySelector('.schedule-error');
    this.preview = root.querySelector('.schedule-preview');
    this.folders = JSON.parse(root.dataset.folders);
    let entries;
    try { entries = JSON.parse(this.json.value); } catch (_) { entries = []; }
    this.entries = (Array.isArray(entries) ? entries : []).filter(entry => entry && typeof entry === 'object').map(entry => ({
      time: typeof entry.time === 'string' ? entry.time : '',
      name: typeof entry.name === 'string' ? entry.name : '',
      media: entry.media === 'videos' ? 'videos' : 'images',
      folders: Array.isArray(entry.folders) ? entry.folders.filter(folder => typeof folder === 'string') : [],
      shuffle: entry.shuffle === true
    }));
    root.querySelector('.schedule-add').addEventListener('click', () => {
      const used = new Set(this.entries.map(entry => entry.time));
      const candidates = ['06:00', '14:00', '18:00', ...Array.from({length: 1440}, (_, i) => this.format(i))];
      this.entries.push({time: candidates.find(time => !used.has(time)), name: '', media: 'images', folders: [], shuffle: false});
      this.render(true);
    });
    root.querySelector('.schedule-example').addEventListener('click', () => {
      this.entries = ['06:00', '14:00', '18:00'].map((time, i) => ({
        time, name: ['Morning', 'Afternoon', 'Evening'][i], media: 'images', folders: [], shuffle: false
      }));
      this.render(true);
    });
    this.mode.addEventListener('change', () => this.update());
    root.closest('form').addEventListener('submit', event => {
      if (this.active() && !this.validate()) {
        event.preventDefault();
        event.stopImmediatePropagation();
        this.error.focus();
      }
    }, true);
    this.render();
  }

  active() { return this.mode.value === 'scheduled'; }
  element(tag, text = '', className = '') {
    const node = document.createElement(tag);
    node.textContent = text;
    node.className = className;
    return node;
  }
  button(text, action) {
    const node = this.element('button', text);
    node.type = 'button';
    node.addEventListener('click', action);
    return node;
  }
  format(minutes) { return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`; }
  minute(time) { const [hour, minute] = time.split(':').map(Number); return hour * 60 + minute; }
  now() { return (this.clock.value.seconds + Math.floor((Date.now() - this.clock.received) / 1000)) % 86400; }

  render(dirty = false) {
    const container = this.root.querySelector('.schedule-slots');
    container.replaceChildren();
    this.rows = this.entries.map((entry, index) => {
      const node = this.element('article', '', 'schedule-slot');
      const controls = this.element('div', '', 'schedule-slot-controls');
      const time = this.element('input');
      time.type = 'time'; time.value = entry.time;
      const timeLabel = this.element('label', 'Start time');
      timeLabel.append(time);
      time.addEventListener('input', () => { entry.time = time.value; this.update(true); });
      const name = this.element('input');
      name.type = 'text'; name.value = entry.name; name.maxLength = 40; name.placeholder = 'Morning, evening…';
      const nameLabel = this.element('label', 'Name (optional)');
      nameLabel.append(name);
      name.addEventListener('input', () => { entry.name = name.value; this.update(true); });
      const media = this.element('select');
      [['images', 'Images / GIFs'], ['videos', 'Videos']].forEach(([value, text]) => {
        const option = this.element('option', text); option.value = value; media.append(option);
      });
      media.value = entry.media;
      const mediaLabel = this.element('label', 'Play');
      mediaLabel.append(media);
      media.addEventListener('change', () => { entry.media = media.value; this.update(true); });
      const shuffle = this.element('input');
      shuffle.type = 'checkbox'; shuffle.checked = entry.shuffle;
      const shuffleLabel = this.element('label', '', 'schedule-shuffle');
      shuffleLabel.append(shuffle, document.createTextNode(' Shuffle'));
      shuffle.addEventListener('change', () => { entry.shuffle = shuffle.checked; this.update(true); });
      const remove = this.button('Remove', () => { this.entries.splice(index, 1); this.render(true); });
      remove.setAttribute('aria-label', `Remove slot ${index + 1}`);
      controls.append(timeLabel, nameLabel, mediaLabel, shuffleLabel, remove);
      const details = this.element('details', '', 'schedule-folder-picker');
      details.open = !entry.folders.length;
      const summary = this.element('summary');
      const search = this.element('input');
      search.type = 'search'; search.placeholder = 'Find folders'; search.setAttribute('aria-label', 'Find folders for this slot');
      search.addEventListener('keydown', event => { if (event.key === 'Enter') event.preventDefault(); });
      const choices = this.element('div', '', 'schedule-folder-options');
      const names = [...new Set([...this.folders, ...entry.folders])];
      const drawChoices = () => {
        choices.replaceChildren();
        names.filter(folder => folder.toLocaleLowerCase().includes(search.value.toLocaleLowerCase())).forEach(folder => {
          const label = this.element('label');
          const checkbox = this.element('input');
          checkbox.type = 'checkbox'; checkbox.value = folder; checkbox.checked = entry.folders.includes(folder);
          checkbox.addEventListener('change', () => {
            entry.folders = checkbox.checked ? [...new Set([...entry.folders, folder])] : entry.folders.filter(name => name !== folder);
            this.update(true);
          });
          label.append(checkbox, document.createTextNode(' ' + folder + (this.folders.includes(folder) ? '' : ' (unavailable)')));
          choices.append(label);
        });
        if (!choices.children.length) choices.textContent = 'No matching folders. Check your media connection or search.';
      };
      const actions = this.element('div', '', 'schedule-actions');
      actions.append(this.button('Select visible', () => {
        entry.folders = [...new Set([...entry.folders, ...names.filter(folder => folder.toLocaleLowerCase().includes(search.value.toLocaleLowerCase()))])];
        drawChoices(); this.update(true);
      }), this.button('Clear selection', () => { entry.folders = []; drawChoices(); this.update(true); }));
      search.addEventListener('input', drawChoices);
      drawChoices();
      details.append(summary, search, actions, choices);
      node.append(controls, details);
      container.append(node);
      return {node, time, summary};
    });
    this.root.querySelector('.schedule-example').hidden = this.entries.length > 0;
    this.root.querySelector('.schedule-add').disabled = this.entries.length >= 48;
    this.update(dirty);
  }

  validate() {
    let error = this.entries.length ? '' : 'Add a time slot to choose what plays.';
    if (this.entries.length > 48) error = 'Use at most 48 time slots.';
    const times = this.entries.map(entry => entry.time);
    this.entries.forEach((entry, i) => {
      let message = '';
      if (!/^(?:[01][0-9]|2[0-3]):[0-5][0-9]$/.test(entry.time)) message = 'Choose a start time.';
      else if (times.filter(time => time === entry.time).length > 1) message = `Two slots start at ${entry.time}. Choose different times.`;
      else if (!entry.folders.length) message = `Choose at least one folder for ${entry.time}.`;
      else if (entry.folders.length > 256) message = 'Use at most 256 folders in a slot.';
      else if (entry.name.length > 40) message = 'Slot names must be at most 40 characters.';
      if (!error) error = message;
      this.rows[i].time.required = this.active();
      this.rows[i].time.setCustomValidity(this.active() ? message : '');
    });
    this.error.textContent = this.active() ? error : '';
    this.problem = error;
    return !error;
  }

  update(dirty = false) {
    this.json.value = JSON.stringify(this.entries);
    if (dirty) this.json.dispatchEvent(new Event('change', {bubbles: true}));
    this.rows.forEach((row, i) => {
      const folders = this.entries[i].folders;
      row.summary.textContent = folders.length ? `${folders.length} folder${folders.length === 1 ? '' : 's'}: ${folders.join(', ')}` : 'Choose folders';
    });
    this.root.querySelectorAll('input:not([type="hidden"]), select').forEach(control => { control.disabled = !this.active(); });
    this.validate();
    this.tick(true);
  }

  tick(force = false) {
    const seconds = this.now();
    const offset = this.clock.value.offset.replace(/([+-][0-9]{2})([0-9]{2})/, '$1:$2');
    const stale = Date.now() - this.clock.received > 120000 ? ' · clock last checked more than 2 minutes ago' : '';
    this.root.querySelector('.schedule-device-clock').textContent = `Device time: ${this.format(Math.floor(seconds / 60))}:${String(seconds % 60).padStart(2, '0')} ${this.clock.value.zone} (UTC${offset})${stale}`;
    const minute = Math.floor(seconds / 60);
    if (!force && minute === this.lastMinute) return;
    this.lastMinute = minute;
    this.preview.replaceChildren();
    if (this.problem) { this.preview.textContent = 'Complete the slots to preview the day.'; return; }
    const sorted = [...this.entries].sort((a, b) => a.time.localeCompare(b.time));
    const active = [...sorted].reverse().find(entry => this.minute(entry.time) <= minute) || sorted[sorted.length - 1];
    this.rows.forEach((row, i) => row.node.classList.toggle('is-current', this.entries[i] === active));
    const next = sorted.find(entry => this.minute(entry.time) > minute);
    const title = sorted.length === 1 ? `Preview now: ${active.name || active.time} · runs all day` : `Preview now: ${active.name || active.time} · next change ${next ? next.time : sorted[0].time + ' tomorrow'}`;
    this.preview.append(this.element('strong', title));
    const ranges = [];
    if (this.minute(sorted[0].time) > 0) ranges.push({start: 0, end: this.minute(sorted[0].time), entry: sorted[sorted.length - 1]});
    sorted.forEach((entry, i) => ranges.push({start: this.minute(entry.time), end: i + 1 < sorted.length ? this.minute(sorted[i + 1].time) : 1440, entry}));
    const bar = this.element('div', '', 'schedule-timeline');
    bar.setAttribute('aria-hidden', 'true');
    const list = this.element('ol', '', 'schedule-day');
    ranges.forEach(({start, end, entry}) => {
      const segment = this.element('span');
      segment.style.flexGrow = end - start;
      segment.style.backgroundColor = ['#5078b4', '#478875', '#9467a5', '#af7b3b'][sorted.indexOf(entry) % 4];
      segment.title = `${this.format(start)}–${this.format(end)} ${entry.name}`;
      bar.append(segment);
      const item = this.element('li', `${this.format(start)}–${this.format(end)} · ${entry.name ? entry.name + ' · ' : ''}${entry.media === 'videos' ? 'Videos' : 'Images/GIFs'} · ${entry.folders.join(', ')}`);
      if (minute >= start && minute < end) { item.className = 'is-current'; item.append(document.createTextNode(' · Now')); }
      list.append(item);
    });
    this.preview.append(bar, list);
  }
}
