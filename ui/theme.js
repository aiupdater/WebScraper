/* WebScraper theme controller. Visual tokens live in app.css; icons and fonts are local. */
(() => {
  const root = document.documentElement;
  const stored = localStorage.getItem('wlw.theme');
  let theme = stored === 'dark' ? 'dark' : 'light';
  let transitioning = false;
  const reduced = () => root.classList.contains('motion-reduced') || matchMedia('(prefers-reduced-motion: reduce)').matches;
  const apply = value => {
    theme = value;
    root.classList.toggle('theme-dark', value === 'dark');
    root.classList.toggle('theme-light', value !== 'dark');
    root.dataset.theme = value;
    const toggle = document.getElementById('theme-toggle');
    if (toggle) {
      toggle.setAttribute('aria-pressed', String(value === 'dark'));
      toggle.setAttribute('aria-label', value === 'dark' ? 'Přepnout světlý režim' : 'Přepnout tmavý režim');
      toggle.title = toggle.getAttribute('aria-label');
      toggle.querySelector('use').setAttribute('href', value === 'dark' ? '#i-sun' : '#i-moon');
    }
  };
  function motion(value) {
    root.classList.toggle('motion-reduced', value);
    root.classList.toggle('motion-full', !value);
    localStorage.setItem('wlw.motion', value ? 'reduced' : 'full');
  }
  apply(theme);
  motion(localStorage.getItem('wlw.motion') === 'reduced');
  const toggle = document.getElementById('theme-toggle');
  toggle.addEventListener('click', async () => {
    if (transitioning) return;
    const next = theme === 'dark' ? 'light' : 'dark';
    localStorage.setItem('wlw.theme', next);
    if (!reduced()) {
      toggle.classList.remove('theme-toggle-animating');
      void toggle.offsetWidth;
      toggle.classList.add('theme-toggle-animating');
      setTimeout(() => toggle.classList.remove('theme-toggle-animating'), 520);
    }
    if (reduced() || !document.startViewTransition) { apply(next); return; }
    transitioning = true;
    try {
      const rect = toggle.getBoundingClientRect();
      const x = rect.left + rect.width / 2, y = rect.top + rect.height / 2;
      const radius = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
      const transition = document.startViewTransition(() => apply(next));
      await transition.ready;
      await root.animate({clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`]},
        {duration: 360, easing: 'ease-out', pseudoElement: '::view-transition-new(root)'}).finished;
      await transition.finished;
    } catch (_) { apply(next); }
    finally { transitioning = false; }
  });
  const checkbox = document.getElementById('reduce-motion');
  checkbox.checked = root.classList.contains('motion-reduced');
  checkbox.addEventListener('change', () => motion(checkbox.checked));
})();
