// update.js - handles update UI
function fetchVersion() {
  fetch('/update/version').then(r=>r.json()).then(data => {
    let info = `<b>Current Version:</b> ${data.local || 'unknown'}<br>`;
    info += `<b>Latest Version:</b> ${data.latest || 'unknown'}<br>`;
    info += `<b>Last Checked:</b> ${data.last_update}`;
    document.getElementById('update-info').innerHTML = info;
    let changelog = '<b>Recent Changes:</b><ul>' + (data.changelog||[]).map(l=>`<li>${l}</li>`).join('') + '</ul>';
    document.getElementById('update-changelog').innerHTML = changelog;
  });
}
function checkUpdate() {
  document.getElementById('update-status').innerHTML = 'Checking for updates...';
  fetch('/update/check', {method:'POST'}).then(r=>r.json()).then(data => {
    let msg = data.up_to_date ? 'Up to date.' : 'Update available!';
    document.getElementById('update-status').innerHTML = msg;
    fetchVersion();
  });
}
function runUpdate() {
  document.getElementById('update-status').innerHTML = 'Updating...';
  fetch('/update/run', {method:'POST'}).then(r=>r.json()).then(data => {
    let msg = data.status === 'success' ? 'Update complete.' : 'Update failed.';
    msg += `<pre style='background:#222;padding:1em;border-radius:8px;'>${data.output}</pre>`;
    document.getElementById('update-status').innerHTML = msg;
    fetchVersion();
  });
}
document.addEventListener('DOMContentLoaded', function() {
  fetchVersion();
  document.getElementById('check-update').onclick = checkUpdate;
  document.getElementById('run-update').onclick = runUpdate;
});
