/* ===================================================================
   lesson-progress.js — generic progress tracker for lesson pages,
   backed by the real per-account API (db.py + app.py), not localStorage.

   Usage on a page:
     <div class="lesson-step" data-step="intro"> ...
       <label class="mark-done-check"><input type="checkbox" data-step-check="intro"> Mark complete</label>
     </div>
     <div class="lesson-progress-track"><div class="lesson-progress-fill" id="lp-fill"></div></div>

   initLessonProgress('single-qubit') wires up every [data-step-check]
   on the page, POSTs checked/unchecked state to
   /api/progress/<lessonId>/step, and keeps #lp-fill / #lp-pct in sync.

   Progress tracking is a real, signed-in-only account feature now
   (checked via window.QS_AUTHENTICATED, set server-side in base.html
   from Flask-Login's current_user — see futureplans.md #10). Signed
   out, the sandbox widgets on a lesson page keep working as normal,
   but checkboxes are disabled and nothing is saved. Gated lesson pages
   (Two Qubits, Physical Qubit, Hardware Lab, Reality Check) are now
   @login_required server-side, so QS_AUTHENTICATED is always true
   there by the time this runs — the "signed out" branch below really
   only matters on the two open lessons, QM Basics and Single Qubit.

   qsFetchAllProgress() — one GET /api/progress call, used by
   dashboard.html / lessons.html / account.html so they don't each make
   one request per lesson.
=================================================================== */

async function qsFetchAllProgress() {
  if (!window.QS_AUTHENTICATED) return {};
  try {
    const res = await fetch('/api/progress');
    if (!res.ok) return {};
    return await res.json(); // { lesson_id: { done: [...], last_visited } }
  } catch (e) {
    return {};
  }
}

function qsComputePct(doneSteps, totalSteps) {
  return totalSteps ? Math.round((doneSteps.length / totalSteps) * 100) : 0;
}

async function recordLessonVisit(lessonId) {
  if (!window.QS_AUTHENTICATED) return;
  try {
    await fetch(`/api/progress/${lessonId}/visit`, {
      method: 'POST',
      headers: { 'X-CSRF-Token': window.QS_CSRF_TOKEN }
    });
  } catch (e) { /* non-critical, ignore */ }
}

async function initLessonProgress(lessonId) {
  const checks = Array.from(document.querySelectorAll('[data-step-check]'));
  const totalSteps = checks.length;
  const fill = document.getElementById('lp-fill');
  const pctLabel = document.getElementById('lp-pct');

  // "Confused here" (student-learning branch, futureplans.md) — one
  // small button per step block, works everywhere for free (built-in
  // AND custom lessons) since every lesson template already marks its
  // step containers with data-step="stepN", not something added
  // per-lesson-type. Signed-out visitors can use this too (an open
  // lesson doesn't need an account to say "this part lost me") — no
  // auth gate on this one, unlike the checkbox progress below it.
  document.querySelectorAll('.lesson-step[data-step]').forEach(stepEl => {
    if (stepEl.querySelector('.confusion-btn')) return; // don't double-inject on re-init
    const stepKey = stepEl.dataset.step;
    const anchor = stepEl.querySelector('.mark-done-check') || stepEl.querySelector('.lesson-step-body') || stepEl;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'confusion-btn';
    btn.style.cssText = 'display:block; margin-top:10px; background:none; border:none; padding:0; font-size:0.78rem; color:var(--text-faint); cursor:pointer; text-decoration:underline; text-underline-offset:2px;';
    btn.textContent = '🤔 Confused by this step?';
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      btn.textContent = 'Sending…';
      try {
        const res = await fetch('/api/confusion', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': window.QS_CSRF_TOKEN },
          body: JSON.stringify({ lesson_id: lessonId, step_key: stepKey })
        });
        btn.textContent = res.ok ? "Thanks — flagged for the creator." : 'Could not send — try again?';
        if (res.ok) setTimeout(() => { btn.disabled = false; btn.textContent = '🤔 Confused by this step?'; }, 4000);
        else btn.disabled = false;
      } catch (e) {
        btn.textContent = 'Could not reach the server.';
        btn.disabled = false;
      }
    });
    anchor.insertAdjacentElement('afterend', btn);
  });

  if (!window.QS_AUTHENTICATED) {
    checks.forEach(c => {
      c.checked = false;
      c.disabled = true;
      const label = c.closest('.mark-done-check');
      if (label) label.title = 'Sign in to save your progress';
    });
    if (pctLabel) pctLabel.textContent = 'Sign in to track';
    if (fill) fill.style.width = '0%';
    const row = pctLabel ? pctLabel.closest('.lesson-progress-row') : null;
    if (row && !row.querySelector('.lp-signin-link')) {
      const a = document.createElement('a');
      a.href = '/login?next=' + encodeURIComponent(location.pathname);
      a.className = 'lp-signin-link';
      a.style.cssText = 'font-size:0.82rem; white-space:nowrap;';
      a.textContent = 'Sign in →';
      row.appendChild(a);
    }
    return;
  }

  recordLessonVisit(lessonId);

  function render(done) {
    checks.forEach(c => {
      const key = c.dataset.stepCheck;
      c.checked = done.includes(key);
      const stepEl = c.closest('.lesson-step');
      if (stepEl) stepEl.classList.toggle('done', c.checked);
    });
    const pct = qsComputePct(done, totalSteps);
    if (fill) fill.style.width = pct + '%';
    if (pctLabel) pctLabel.textContent = pct + '%';
  }

  // Initial state: one GET, reused across every lesson page via the
  // all-progress endpoint so this file doesn't need a second route.
  let done = [];
  try {
    const all = await qsFetchAllProgress();
    done = (all[lessonId] && all[lessonId].done) || [];
  } catch (e) { /* start empty on failure */ }
  render(done);

  checks.forEach(c => {
    c.addEventListener('change', async () => {
      const key = c.dataset.stepCheck;
      // Optimistic UI: update immediately, reconcile with the server's
      // response (steps toggled quickly in a row shouldn't race and
      // clobber each other since the server always returns the full
      // current list, not a delta).
      if (c.checked && !done.includes(key)) done = [...done, key];
      if (!c.checked) done = done.filter(k => k !== key);
      render(done);

      try {
        const res = await fetch(`/api/progress/${lessonId}/step`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': window.QS_CSRF_TOKEN },
          body: JSON.stringify({ step_id: key, done: c.checked })
        });
        if (res.ok) {
          const data = await res.json();
          done = data.done || done;
          render(done);
        }
      } catch (e) { /* keep optimistic state on network failure */ }
    });
  });
}
