/* ===================================================================
   lesson-progress.js — tiny generic progress tracker for lesson pages.

   Usage on a page:
     <div class="lesson-step" data-step="intro"> ... 
       <label class="mark-done-check"><input type="checkbox" data-step-check="intro"> Mark complete</label>
     </div>
     <div class="lesson-progress-track"><div class="lesson-progress-fill" id="lp-fill"></div></div>

   initLessonProgress('single-qubit') wires up every [data-step-check]
   on the page, persists checked state to localStorage under a
   lesson-specific key, and keeps #lp-fill / #lp-pct in sync.
   Also exposes getLessonProgress(lessonId) for the dashboard to read.
=================================================================== */

function lessonStorageKey(lessonId) { return `qs_lesson_progress_${lessonId}`; }

function getLessonProgress(lessonId, totalSteps) {
  try {
    const raw = localStorage.getItem(lessonStorageKey(lessonId));
    const done = raw ? JSON.parse(raw) : [];
    const pct = totalSteps ? Math.round((done.length / totalSteps) * 100) : 0;
    return { done, pct };
  } catch (e) { return { done: [], pct: 0 }; }
}

function initLessonProgress(lessonId) {
  const checks = Array.from(document.querySelectorAll('[data-step-check]'));
  const totalSteps = checks.length;
  const fill = document.getElementById('lp-fill');
  const pctLabel = document.getElementById('lp-pct');

  function load() {
    try { return JSON.parse(localStorage.getItem(lessonStorageKey(lessonId)) || '[]'); }
    catch (e) { return []; }
  }
  function save(done) {
    localStorage.setItem(lessonStorageKey(lessonId), JSON.stringify(done));
  }
  function render() {
    const done = load();
    checks.forEach(c => {
      const key = c.dataset.stepCheck;
      c.checked = done.includes(key);
      const stepEl = c.closest('.lesson-step');
      if (stepEl) stepEl.classList.toggle('done', c.checked);
    });
    const pct = totalSteps ? Math.round((done.length / totalSteps) * 100) : 0;
    if (fill) fill.style.width = pct + '%';
    if (pctLabel) pctLabel.textContent = pct + '%';
  }

  checks.forEach(c => {
    c.addEventListener('change', () => {
      let done = load();
      const key = c.dataset.stepCheck;
      if (c.checked && !done.includes(key)) done.push(key);
      if (!c.checked) done = done.filter(k => k !== key);
      save(done);
      render();
    });
  });

  render();
}
