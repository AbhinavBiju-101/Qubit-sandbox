/*
 * gamification.js — site-wide activity heartbeat for signed-in users.
 *
 * Every 60s, while the tab is visible/focused, POSTs /api/activity/ping
 * (one "minute studied" for today). The server re-checks every badge
 * condition on each ping and returns any freshly-earned ones, which
 * pop a small toast here. This file is loaded on every page (see
 * base.html) so streaks/hours count time spent anywhere in the app,
 * not just on lesson pages specifically.
 *
 * Deliberately coarse: this is "were you actively here" for gamified
 * stats, not a precise or billing-grade timer.
 */
(function () {
  if (!window.QS_AUTHENTICATED) return;

  const PING_INTERVAL_MS = 60 * 1000;
  let timer = null;

  // Mirrors db.BADGE_CATALOG in db.py — kept small and duplicated
  // here rather than round-tripping through the template, since this
  // file is loaded on every page (including signed-out ones, where it
  // no-ops at the top) and the badge metadata rarely changes.
  const BADGE_CATALOG = {
    'streak-3':        { label: '3-Day Streak',     emoji: '🔥' },
    'streak-7':        { label: 'Week Warrior',      emoji: '🗓️' },
    'streak-30':       { label: 'Month Master',      emoji: '🏆' },
    'weekend-studier': { label: 'Weekend Studier',   emoji: '🌤️' },
    'hours-10':        { label: '10 Hours In',       emoji: '⏱️' },
    'hours-40':        { label: '40 Hour Club',      emoji: '💪' },
    'first-lesson':    { label: 'First Steps',       emoji: '🎯' },
    'five-lessons':    { label: 'Getting Serious',   emoji: '📚' },
    'module-1-done':   { label: 'Module 1 Complete', emoji: '🎓' },
    'early-bird':      { label: 'Early Bird',        emoji: '🌅' },
    'night-owl':       { label: 'Night Owl',         emoji: '🦉' },
  };

  function showBadgeToast(badgeKey) {
    const meta = BADGE_CATALOG[badgeKey];
    const label = meta ? `${meta.emoji || '🏅'} ${meta.label}` : 'New badge unlocked!';
    const toast = document.createElement('div');
    toast.className = 'qs-badge-toast';
    toast.innerHTML = `<strong>Badge unlocked</strong><div>${label}</div>`;
    document.body.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('show'));
    setTimeout(() => {
      toast.classList.remove('show');
      setTimeout(() => toast.remove(), 400);
    }, 4200);
  }

  async function ping() {
    if (document.visibilityState !== 'visible') return;
    try {
      const res = await fetch('/api/activity/ping', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': window.QS_CSRF_TOKEN },
        body: JSON.stringify({ local_hour: new Date().getHours() }),
      });
      if (!res.ok) return;
      const data = await res.json();
      (data.newly_earned || []).forEach((key, i) => setTimeout(() => showBadgeToast(key), i * 600));
    } catch (e) {
      // offline / server down — silently skip this tick, try again next interval
    }
  }

  // One ping shortly after load (so a short visit still counts), then
  // on the interval, only while the tab is actually visible.
  setTimeout(ping, 5000);
  timer = setInterval(ping, PING_INTERVAL_MS);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') ping();
  });
})();
