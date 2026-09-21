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
  // Module 2 — Quantum Algorithms
  { id: 'quantum-teleportation', title: 'Quantum Teleportation', href: '/quantum-teleportation', steps: 4, gated: true, tag: 'Module 2 · Lesson 1' },
  { id: 'superdense-coding', title: 'Superdense Coding', href: '/superdense-coding', steps: 4, gated: true, tag: 'Module 2 · Lesson 2' },
  { id: 'deutsch-jozsa', title: 'Deutsch-Jozsa', href: '/deutsch-jozsa', steps: 4, gated: true, tag: 'Module 2 · Lesson 3' },
  { id: 'grovers-search', title: "Grover's Search", href: '/grovers-search', steps: 4, gated: true, tag: 'Module 2 · Lesson 4' },
  // Module 3 — The Physics and Math Underneath
  { id: 'complex-numbers', title: 'Complex Numbers', href: '/complex-numbers', steps: 3, gated: true, tag: 'Module 3 · Lesson 1' },
  { id: 'bra-ket', title: 'Bra-Ket, Demystified', href: '/bra-ket', steps: 3, gated: true, tag: 'Module 3 · Lesson 2' },
  { id: 'matrices-as-gates', title: 'Matrices as Gates', href: '/matrices-as-gates', steps: 3, gated: true, tag: 'Module 3 · Lesson 3' },
  { id: 'measurement-postulate', title: 'Measurement & Stern-Gerlach', href: '/measurement-postulate', steps: 3, gated: true, tag: 'Module 3 · Lesson 4' },
  { id: 'schrodinger-equation', title: 'The Schrödinger Equation', href: '/schrodinger-equation', steps: 3, gated: true, tag: 'Module 3 · Lesson 5' },
  { id: 'basis-vectors', title: 'Basis Vectors & Hilbert Space', href: '/basis-vectors', steps: 3, gated: true, tag: 'Module 3 · Lesson 6' },
  { id: 'tensor-products', title: 'Tensor Products', href: '/tensor-products', steps: 3, gated: true, tag: 'Module 3 · Lesson 7' },
  { id: 'operator-types', title: 'Hermitian, Unitary & Projection Operators', href: '/operator-types', steps: 3, gated: true, tag: 'Module 3 · Lesson 8' },
  { id: 'eigenvalues-eigenvectors', title: 'Eigenvalues and Eigenvectors', href: '/eigenvalues-eigenvectors', steps: 3, gated: true, tag: 'Module 3 · Lesson 9' },
  { id: 'commutation-relations', title: 'Commutation Relations', href: '/commutation-relations', steps: 3, gated: true, tag: 'Module 3 · Lesson 10' },
  // Module 4 — Where Quantum Comes From
  { id: 'wave-particle-duality', title: 'Wave-Particle Duality', href: '/wave-particle-duality', steps: 3, gated: true, tag: 'Module 4 · Lesson 1' },
  { id: 'blackbody-radiation', title: 'Blackbody Radiation', href: '/blackbody-radiation', steps: 3, gated: true, tag: 'Module 4 · Lesson 2' },
  { id: 'de-broglie', title: 'The de Broglie Wavelength', href: '/de-broglie', steps: 3, gated: true, tag: 'Module 4 · Lesson 3' },
  { id: 'particle-in-a-box', title: 'Particle in a Box', href: '/particle-in-a-box', steps: 3, gated: true, tag: 'Module 4 · Lesson 4' },
  { id: 'quantum-tunneling', title: 'Quantum Tunneling', href: '/quantum-tunneling', steps: 3, gated: true, tag: 'Module 4 · Lesson 5' },
  { id: 'three-dimensional-box', title: 'The 3D Box', href: '/three-dimensional-box', steps: 3, gated: true, tag: 'Module 4 · Lesson 6' },
  // Module 5 — Error Correction & Noise
  { id: 'decoherence', title: 'Why Qubits Decohere', href: '/decoherence', steps: 3, gated: true, tag: 'Module 5 · Lesson 1' },
  { id: 'bit-flip-code', title: 'Bit-Flip and Phase-Flip Codes', href: '/bit-flip-code', steps: 3, gated: true, tag: 'Module 5 · Lesson 2' },
  { id: 'nisq', title: 'NISQ', href: '/nisq', steps: 3, gated: true, tag: 'Module 5 · Lesson 3' },
  // Module 6 — Quantum Cryptography
  { id: 'bb84', title: 'BB84 Key Distribution', href: '/bb84', steps: 3, gated: true, tag: 'Module 6 · Lesson 1' },
  { id: 'shors-algorithm', title: 'Why Factoring Matters', href: '/shors-algorithm', steps: 3, gated: true, tag: 'Module 6 · Lesson 2' },
];
