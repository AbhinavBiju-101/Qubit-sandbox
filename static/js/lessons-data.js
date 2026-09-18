/* ===================================================================
   lessons-data.js — single source of truth for "what lessons exist,
   how many steps do they have, are they gated" — read by dashboard.html
   (Continue list + stats), lessons.html (full grid), and account.html
   (per-lesson progress). Update this list, not each page separately,
   when a lesson's step count changes or a new lesson ships.

   `steps` must match the number of [data-step-check] elements on that
   lesson's own template (checked in initLessonProgress()) — there's no
   automatic sync, it's just tracked here for now.
=================================================================== */

const QS_LESSON_DEFS = [
  { id: 'qm-basics', title: 'QM Basics', href: '/qm-basics', steps: 3, gated: false, tag: 'Lesson 0 · Start here' },
  { id: 'single-qubit', title: 'Single Qubit', href: '/single-qubit', steps: 5, gated: false, tag: 'Lesson 1 · Superposition' },
  { id: 'two-qubit', title: 'Two Qubits', href: '/two-qubit', steps: 3, gated: true, tag: 'Lesson 2 · Measurement' },
  { id: 'physical-qubit', title: 'Physical Qubit', href: '/physical-qubit', steps: 4, gated: true, tag: 'Lesson 3 · Hardware' },
  { id: 'hardware-lab', title: 'Hardware Lab', href: '/hardware-lab', steps: 3, gated: true, tag: 'Lesson 4 · Deep Dive' },
  { id: 'reality-check', title: 'Reality Check', href: '/reality-check', steps: 4, gated: true, tag: 'Lesson 5 · Scaling' },
];
