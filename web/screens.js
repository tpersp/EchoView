// screens.js - handles device info, slideshow state, and screen settings UI
const MODES = [
  { value: 'specific_file', label: 'Specific File' },
  { value: 'random_file', label: 'Random (All Folders)' },
  { value: 'mixed', label: 'Mixed (Files/Folders)' },
  { value: 'spotify', label: 'Spotify' }
];

function fetchDeviceInfo() {
  fetch('/device-info').then(r=>r.json()).then(info => {
    let temp = info.temp !== null ? `${info.temp}°C` : 'N/A';
    let memUsed = (info.mem_used/1024/1024).toFixed(0);
    let memTotal = (info.mem_total/1024/1024).toFixed(0);
    document.getElementById('device-info').innerHTML = `
      <b>Hostname:</b> ${info.hostname}<br>
      <b>OS:</b> ${info.os}<br>
      <b>CPU Usage:</b> ${info.cpu_percent}%<br>
      <b>Memory:</b> ${memUsed} / ${memTotal} MB (${info.mem_percent}%)<br>
      <b>Temperature:</b> ${temp}
    `;
  });
}

function fetchMode() {
  fetch('/screen-settings').then(r=>r.json()).then(settings => {
    let modeRow = document.getElementById('mode-row');
    if (!modeRow) return;
    let curMode = settings.mode || 'random_file';
    let html = `<label for='mode-select'><b>Slideshow Mode:</b></label> <select id='mode-select'>`;
    for (let m of MODES) {
      html += `<option value='${m.value}'${curMode===m.value?' selected':''}>${m.label}</option>`;
    }
    html += `</select>`;
    modeRow.innerHTML = html;
    document.getElementById('mode-select').onchange = function() {
      setMode(this.value);
    };
  });
}

function setMode(mode) {
  let fd = new FormData();
  fd.append('mode', mode);
  fetch('/screen-settings', {method:'POST', body:fd})
    .then(()=>{
      fetchMode();
      fetchState();
    });
}

function fetchScreenSettings() {
  fetch('/screen-settings').then(r=>r.json()).then(settings => {
    let el = document.getElementById('screen-settings');
    if (!el) return;
    let html = `<div style='margin-bottom:1em;'><b>Current Mode:</b> ${settings.mode || 'random_file'}`;
    if (settings.mode === 'specific_file' && settings.specific_file) {
      html += `<br><b>File:</b> ${settings.specific_file}`;
    } else if (settings.mode === 'random_file') {
      html += `<br><b>Folder:</b> ${settings.random_folder || 'ALL'}`;
    } else if (settings.mode === 'mixed') {
      html += `<br><b>Files:</b> ${(settings.mixed_files||[]).join(', ')}`;
      html += `<br><b>Folders:</b> ${(settings.mixed_folders||[]).join(', ')}`;
    } else if (settings.mode === 'spotify') {
      html += `<br><b>Spotify Mode Enabled</b>`;
    }
    html += `</div>`;
    el.innerHTML = html;
  });
}

function fetchState() {
  fetch('/slideshow').then(r=>r.json()).then(state => {
    document.getElementById('slideIdx').max = state.files.length-1;
    document.getElementById('slideIdx').value = state.current;
    document.getElementById('interval').value = state.interval || 5;
    let cur = state.files.length ? `Current: <b>${state.files[state.current]}</b> (${state.current+1}/${state.files.length})` : 'No media.';
    document.getElementById('current').innerHTML = cur;
    let list = state.files.map((f,i)=>`<li${i==state.current?" style=\"font-weight:bold\"":''}>${i+1}. <a href='/media/${f}' target='_blank'>${f}</a></li>`).join('');
    document.getElementById('media-list').innerHTML = `<ul>${list}</ul>`;
    fetchScreenSettings();
  });
}

function nextSlide() {
  fetch('/slideshow/next', {method:'POST'}).then(fetchState);
}
function prevSlide() {
  fetch('/slideshow/prev', {method:'POST'}).then(fetchState);
}
function setSlide(e) {
  e.preventDefault();
  let idx = document.getElementById('slideIdx').value;
  let fd = new FormData(); fd.append('idx', idx);
  fetch('/slideshow/set', {method:'POST', body:fd}).then(fetchState);
}
function setInterval(e) {
  e.preventDefault();
  let interval = document.getElementById('interval').value;
  let fd = new FormData(); fd.append('interval', interval);
  fetch('/slideshow/interval', {method:'POST', body:fd}).then(fetchState);
}
document.addEventListener('DOMContentLoaded', function() {
  fetchDeviceInfo();
  setInterval(fetchDeviceInfo, 5000);
  fetchMode(); // Only call fetchMode() once on load
  fetchState();
  setInterval(fetchState, 2000);
});
