/* ===================================================================
   chrome.js — shared nav + footer, injected so every page stays
   in sync without hand-editing five copies of the same markup.
=================================================================== */

(function () {
  const PAGES = [
    { href: '/', label: 'Home', key: 'home' },
    { href: '/single-qubit', label: 'Single Qubit', key: 'single' },
    { href: '/two-qubit', label: 'Two Qubits', key: 'two' },
    { href: '/physical-qubit', label: 'Physical Qubit', key: 'physical' },
    { href: '/reality-check', label: 'Reality Check', key: 'reality' },
  ];

  const current = document.body.getAttribute('data-page');

  const nav = document.createElement('header');
  nav.className = 'topnav';
  nav.innerHTML = `
    <div class="shell">
      <a class="brand" href="/" style="text-decoration:none;">
        <span class="dot"></span> Qubit Sandbox
      </a>
      <nav class="pages">
        ${PAGES.map(p => `<a href="${p.href}"${p.key === current ? ' class="active"' : ''}>${p.label}</a>`).join('')}
      </nav>
    </div>
  `;
  document.body.insertBefore(nav, document.body.firstChild);

  const footer = document.createElement('footer');
  footer.className = 'site';
  footer.innerHTML = `
    <div class="shell">
      Qubit Sandbox &mdash; built for a hackathon problem set on single-qubit,
      two-qubit, and physical qubit systems. Runs entirely client-side; the
      quantum "simulation" is real 2×2 complex matrix math, not canned numbers.
    </div>
  `;
  document.body.appendChild(footer);
})();
