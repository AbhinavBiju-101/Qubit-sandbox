/* ===================================================================
   sidebar.js — collapse/expand on desktop (persisted), slide-over
   drawer on mobile. No frameworks, just a few DOM listeners.
=================================================================== */
(function () {
  const sidebar = document.getElementById('sidebar');
  const collapseBtn = document.getElementById('sidebar-toggle');
  const mobileBtn = document.getElementById('sidebar-toggle-mobile');
  const scrim = document.getElementById('sidebar-scrim');

  // desktop collapse state, remembered across pages
  const KEY = 'qs_sidebar_collapsed';
  if (localStorage.getItem(KEY) === '1') sidebar.classList.add('collapsed');

  collapseBtn && collapseBtn.addEventListener('click', () => {
    sidebar.classList.toggle('collapsed');
    localStorage.setItem(KEY, sidebar.classList.contains('collapsed') ? '1' : '0');
  });

  // mobile drawer
  function openMobile() { sidebar.classList.add('mobile-open'); scrim.classList.add('show'); }
  function closeMobile() { sidebar.classList.remove('mobile-open'); scrim.classList.remove('show'); }

  mobileBtn && mobileBtn.addEventListener('click', openMobile);
  scrim && scrim.addEventListener('click', closeMobile);
  document.querySelectorAll('.sidebar-nav a').forEach(a => a.addEventListener('click', closeMobile));
})();
