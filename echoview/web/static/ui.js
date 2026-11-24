// Small shell interactions; all settings and media operations stay in their existing forms.
document.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.getElementById('app-navigation');
  const toggle = document.getElementById('nav-toggle');
  const close = document.getElementById('nav-close');
  const scrim = document.getElementById('nav-scrim');
  const main = document.getElementById('main-content');
  const mobileHeader = document.querySelector('.mobile-header');
  const media = window.matchMedia('(max-width: 767.98px)');
  function setNavigation(open, restoreFocus = true) {
    const visible = media.matches && open;
    sidebar.classList.toggle('open', visible);
    document.body.classList.toggle('nav-open', visible);
    sidebar.inert = media.matches && !visible;
    sidebar.setAttribute('aria-hidden', String(media.matches && !visible));
    toggle.setAttribute('aria-expanded', String(visible));
    scrim.hidden = !visible;
    main.inert = visible;
    mobileHeader.inert = visible;
    if (visible) close.focus();
    else if (restoreFocus && media.matches) toggle.focus();
  }
  toggle.addEventListener('click', () => setNavigation(!sidebar.classList.contains('open')));
  close.addEventListener('click', () => setNavigation(false));
  scrim.addEventListener('click', () => setNavigation(false));
  media.addEventListener('change', () => setNavigation(false, false));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && sidebar.classList.contains('open')) setNavigation(false);
  });
  setNavigation(false, false);
  document.querySelectorAll('[data-open-details]').forEach(button => {
    button.addEventListener('click', () => {
      const target = document.getElementById(button.dataset.openDetails);
      if (!target) return;
      target.open = true;
      target.querySelector('summary').focus();
      target.scrollIntoView({block: 'nearest'});
    });
  });
  document.addEventListener('keydown', event => {
    const item = event.target.closest('.mixed-item');
    if (item && ['Enter', ' '].includes(event.key)) { event.preventDefault(); item.click(); }
    if (event.key === 'Escape') {
      document.querySelectorAll('.file-item.open').forEach(file => {
        file.classList.remove('open');
        const button = file.querySelector('.file-options-btn');
        button?.setAttribute('aria-expanded', 'false');
        button?.focus();
      });
    }
  });
});

// This action never submits or reloads the page's settings forms.
document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('identify-displays-form');
  if (!form) return;
  const button = form.querySelector('button');
  const label = button.querySelector('span');
  const status = document.getElementById('identify-displays-status');
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (button.disabled) return;
    button.disabled = true; status.textContent = ''; label.textContent = 'Identifying…';
    try {
      const response = await fetch(form.action, {method: 'POST', headers: {'Accept': 'application/json'}, signal: AbortSignal.timeout(6000)});
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.error || 'Could not identify displays.');
      setTimeout(() => { button.disabled = false; label.textContent = 'Identify displays'; }, 5000);
    } catch (error) {
      status.textContent = error.name === 'TimeoutError' ? 'Viewer did not respond. Try again.' : error.name === 'TypeError' ? 'Could not reach viewer. Try again.' : error.message;
      button.disabled = false; label.textContent = 'Identify displays';
    }
  });
});
