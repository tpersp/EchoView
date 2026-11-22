// Current status only. No media probes, settings writes or automatic restarts.
document.addEventListener('DOMContentLoaded', () => {
  const panel=document.querySelector('[data-recovery-panel]');
  if (!panel) return;
  const list=panel.querySelector('[data-recovery-issues]'),feedback=panel.querySelector('[data-recovery-feedback]');
  let timer,request,signature='',viewer=null,restarting=false,previousViewer=null,deadline=0,suspended=false,requestingRestart=false;
  const message=text=>{feedback.textContent=text;feedback.hidden=!text;};
  function render(issues) {
    const key=JSON.stringify(issues);
    panel.hidden=panel.dataset.alwaysVisible!=='true' && !issues.length && !restarting && feedback.hidden;
    panel.classList.toggle('has-issues',!!issues.length);
    if (key===signature) return;
    signature=key;list.replaceChildren();
    if (!issues.length && panel.dataset.alwaysVisible==='true') {
      const healthy=document.createElement('p');healthy.className='recovery-healthy';healthy.textContent='Viewer is responding. No playback problems reported.';list.append(healthy);
    }
    for (const issue of issues) {
      const row=document.createElement('div');row.className='recovery-row';
      const text=document.createElement('div'),title=document.createElement('strong'),detail=document.createElement('p');
      title.textContent=(issue.display?`${issue.display} · `:'')+issue.title;detail.textContent=issue.detail;
      text.append(title,detail);row.append(text);
      const actions=document.createElement('div');actions.className='form-actions';
      if (['media','spotify','displays'].includes(issue.action)) {
        const link=document.createElement('a');link.className='button quiet';link.href=panel.dataset[issue.action+'Url'];
        link.textContent={media:'Choose media',spotify:'Spotify settings',displays:'Display settings'}[issue.action];actions.append(link);
      }
      if (['restart','retry','media'].includes(issue.action)) {
        const button=document.createElement('button');button.type='button';button.className='quiet';button.textContent='Restart viewer';
        button.disabled=restarting;button.addEventListener('click',restart);actions.append(button);
      }
      if (issue.code==='viewer_unavailable') {
        const link=document.createElement('a');link.className='button quiet';link.href=panel.dataset.logUrl;link.textContent='Download logs';actions.append(link);
      }
      row.append(actions);list.append(row);
    }
  }
  async function restart() {
    if (restarting) return;
    restarting=true;requestingRestart=true;previousViewer=viewer || 0;deadline=Date.now()+30000;
    message('Restarting viewer…');list.querySelectorAll('button').forEach(button=>button.disabled=true);
    const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),20000);
    let failure='Viewer restart could not be confirmed. Check status and logs before retrying.';
    try {
      const response=await fetch(panel.dataset.restartUrl,{method:'POST',headers:{Accept:'application/json'},signal:controller.signal});
      const data=await response.json();
      if (!response.ok) { if (typeof data.error==='string') failure=data.error;throw new Error('Restart failed'); }
      message(data.message);refresh();
    } catch (error) {
      restarting=false;message(controller.signal.aborted?'Restart outcome is unknown. Check status before retrying.':failure);
      list.querySelectorAll('button').forEach(button=>button.disabled=false);
    } finally {clearTimeout(timeout);requestingRestart=false;refresh();}
  }
  async function refresh() {
    clearTimeout(timer);
    if (document.hidden || suspended || request) return;
    const controller=new AbortController();request=controller;
    const timeout=setTimeout(()=>controller.abort(),8000);
    try {
      const response=await fetch(panel.dataset.url,{cache:'no-store',signal:controller.signal});
      if (!response.ok) throw new Error('Status unavailable');
      const data=await response.json();viewer=data.viewer;
      if (!requestingRestart && previousViewer!==null && viewer && viewer!==previousViewer) { restarting=false;previousViewer=null;message('');signature=''; }
      if (restarting && Date.now()>deadline) { restarting=false;message('Viewer has not reported back yet. Check the logs before retrying.');signature=''; }
      render(data.issues);
    } catch (error) {
      if (controller.signal.aborted && document.hidden) return;
      render([{code:'connection',title:'Cannot check playback status',detail:'Check the connection to this EchoView device.'}]);
    } finally {
      clearTimeout(timeout);if (request===controller) request=null;
      if (!document.hidden && !suspended) timer=setTimeout(refresh,5000);
    }
  }
  panel.querySelector('[data-recovery-refresh]').addEventListener('click',()=>{if (!restarting) message('');refresh();});
  document.addEventListener('visibilitychange',()=>{clearTimeout(timer);if (document.hidden) request?.abort();else refresh();});
  window.addEventListener('pagehide',()=>{suspended=true;clearTimeout(timer);request?.abort();});
  window.addEventListener('pageshow',()=>{suspended=false;refresh();});
  refresh();
});
