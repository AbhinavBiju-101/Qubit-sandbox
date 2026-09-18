/* ===================================================================
   auth.js — mock "signed in" state, localStorage-based.

   There's no real backend auth yet. This exists so lesson-locking and
   per-account progress tracking can be built and demoed now, and swapped
   for real sessions later without touching every page that calls these
   functions. When Google OAuth lands (see futureplans.md), only this
   file plus the /login route should need to change — everything else
   already calls qsIsSignedIn() / qsCurrentUser() rather than checking
   localStorage directly.

   Storage:
     qs_signed_in — "1" | "0"
     qs_user      — JSON: { name, email, provider }
=================================================================== */

const QS_AUTH_KEY = 'qs_signed_in';
const QS_USER_KEY = 'qs_user';

function qsIsSignedIn() {
  try { return localStorage.getItem(QS_AUTH_KEY) === '1'; }
  catch (e) { return false; }
}

function qsCurrentUser() {
  try { return JSON.parse(localStorage.getItem(QS_USER_KEY) || 'null'); }
  catch (e) { return null; }
}

/** Mock sign-in. `user` is optional — defaults to a demo guest identity.
 *  Swap this implementation for a real OAuth callback later; every
 *  caller already just does qsSignIn() / qsSignIn(user). */
function qsSignIn(user) {
  const u = user || { name: 'Demo Guest', email: 'guest@example.com', provider: 'demo' };
  try {
    localStorage.setItem(QS_AUTH_KEY, '1');
    localStorage.setItem(QS_USER_KEY, JSON.stringify(u));
  } catch (e) { /* ignore, e.g. storage disabled */ }
  return u;
}

function qsSignOut() {
  try {
    localStorage.setItem(QS_AUTH_KEY, '0');
    localStorage.removeItem(QS_USER_KEY);
  } catch (e) { /* ignore */ }
}

/** Renders the small "Sign in" / "Hi, Name · Sign out" control used in
 *  the sidebar footer. Pass the container element; safe no-op if null. */
function qsRenderAuthStatus(el) {
  if (!el) return;
  if (qsIsSignedIn()) {
    const u = qsCurrentUser();
    const name = (u && u.name) ? u.name : 'Account';
    el.innerHTML = `<span class="muted">Hi, ${name.split(' ')[0]}</span> · <a href="#" id="qs-signout-link">Sign out</a>`;
    const link = el.querySelector('#qs-signout-link');
    if (link) link.addEventListener('click', (e) => {
      e.preventDefault();
      qsSignOut();
      location.reload();
    });
  } else {
    el.innerHTML = `<a href="/login">Sign in</a>`;
  }
}
