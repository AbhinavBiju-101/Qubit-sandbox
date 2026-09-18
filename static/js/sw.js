/* ===================================================================
   sw.js — minimal service worker for PWA installability + basic
   offline support. Served at the ROOT path (/sw.js) via a dedicated
   Flask route (see app.py) rather than /static/js/sw.js, because a
   service worker can only control paths at or below its own URL —
   root scope requires a root-level script path.

   Strategy: cache-first for the app shell (HTML pages + static
   assets), so once you've visited a page it works offline; anything
   not in the precache list falls through to the network as normal.

   Note on gated pages: Two Qubits, Physical Qubit, Hardware Lab,
   Reality Check, and Account are all `@login_required` server-side now
   (see app.py / futureplans.md #10) — an unauthenticated fetch of any
   of them returns a redirect to /login, and since fetch() follows
   redirects by default, blindly precaching those URLs would cache the
   /login PAGE's content under the WRONG cache key. They're
   deliberately left out of PRECACHE_URLS below for that reason. Once
   you've actually signed in and visited one in-browser, the browser's
   normal HTTP cache / this worker's runtime fetches handle it fine —
   this file only controls the *install-time* precache, not every
   request. /api/compare-shots(-2q) and /api/progress* are intentionally
   NOT cached either way — live server computation and per-account
   data, not static assets.
=================================================================== */

const CACHE_NAME = 'qubit-sandbox-v3';

const PRECACHE_URLS = [
  '/',
  '/dashboard',
  '/lessons',
  '/demos',
  '/demos/coin-flip',
  '/embed/coin-flip',
  '/embed/two-qubit',
  '/qm-basics',
  '/single-qubit',
  '/sandbox',
  '/lesson-creator',
  '/python-ide',
  '/login',
  '/static/css/style.css',
  '/static/js/quantum.js',
  '/static/js/twoqubit.js',
  '/static/js/bloch.js',
  '/static/js/sidebar.js',
  '/static/js/lesson-progress.js',
  '/static/js/lessons-data.js',
  '/static/js/stats.js',
  '/static/manifest.json',
  '/static/favicon.ico',
  '/static/images/logo.svg',
  '/static/images/apple-touch-icon.png',
  '/static/images/favicon-32x32.png',
  '/static/images/icon-192.png',
  '/static/images/icon-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS)).catch(() => {
      // If precaching fails (e.g. a route 404s), don't block install —
      // the app should still work online even if offline caching is incomplete.
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(names.filter((n) => n !== CACHE_NAME).map((n) => caches.delete(n)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return; // never intercept POSTs (the API endpoints)
  if (req.url.includes('/api/')) return; // never cache the Qiskit/progress APIs — always hit the network

  event.respondWith(
    caches.match(req).then((cached) => {
      const networkFetch = fetch(req)
        .then((res) => {
          // Only cache successful, non-redirected responses — a followed
          // redirect (e.g. an @login_required page bouncing to /login)
          // still resolves with status 200, so checking status alone
          // isn't enough; `res.redirected` is what actually catches it.
          // See the top-of-file note for why this matters here.
          if (res && res.status === 200 && !res.redirected) {
            const copy = res.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
          }
          return res;
        })
        .catch(() => cached); // offline and not cached: nothing we can do

      return cached || networkFetch;
    })
  );
});
