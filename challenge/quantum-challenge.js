/* ===================================================================
   quantum-challenge.js — YOUR job: fill in the TODOs below.

   This is Hackathon Problem 1 ("Coin Flip, But Quantum") stripped
   down to a skeleton. The complex-number helper (C) and the generic
   matrix-application machinery are given, because that's just
   plumbing — the actual physics is the gate matrices and the
   measurement logic, and that part is on you.

   Reference: index.html already wires up buttons that call
   q.H(), q.X(), q.Y(), q.Z(), q.RY(theta), and q.sampleShots(1000) —
   so once you implement the methods below, the page should come
   alive with no other changes needed.
=================================================================== */

const C = {
  make: (re, im = 0) => ({ re, im }),
  add: (a, b) => ({ re: a.re + b.re, im: a.im + b.im }),
  mul: (a, b) => ({ re: a.re * b.re - a.im * b.im, im: a.re * b.im + a.im * b.re }),
  scale: (a, s) => ({ re: a.re * s, im: a.im * s }),
  abs2: (a) => a.re * a.re + a.im * a.im,
  abs: (a) => Math.sqrt(a.re * a.re + a.im * a.im),
  arg: (a) => Math.atan2(a.im, a.re),
  fmt: (a, d = 3) => {
    const re = a.re.toFixed(d), im = Math.abs(a.im).toFixed(d);
    if (Math.abs(a.im) < 1e-9) return `${re}`;
    return `${re} ${a.im >= 0 ? '+' : '-'} ${im}i`;
  }
};

const SQRT1_2 = 1 / Math.sqrt(2);

/**
 * A single-qubit pure state: two complex amplitudes.
 *   this.a = amplitude of |0>
 *   this.b = amplitude of |1>
 * Physical requirement: |a|^2 + |b|^2 must always equal 1.
 */
class Qubit {
  constructor() {
    this.a = C.make(1, 0); // start in |0>
    this.b = C.make(0, 0);
    this.log = [];
  }

  /** Given — applies a 2x2 matrix of complex entries to (a, b).
   *  You should NOT need to touch this; use it inside each gate below. */
  applyMatrix(m, label) {
    const a2 = C.add(C.mul(m[0][0], this.a), C.mul(m[0][1], this.b));
    const b2 = C.add(C.mul(m[1][0], this.a), C.mul(m[1][1], this.b));
    this.a = a2; this.b = b2;
    this.normalize();
    if (label) this.log.push(label);
    return this;
  }

  /** Given — cleans up floating-point drift so |a|^2+|b|^2 stays 1. */
  normalize() {
    const n = Math.sqrt(C.abs2(this.a) + C.abs2(this.b));
    if (n > 1e-12) { this.a = C.scale(this.a, 1 / n); this.b = C.scale(this.b, 1 / n); }
  }

  reset() { this.a = C.make(1, 0); this.b = C.make(0, 0); this.log = []; return this; }

  // -----------------------------------------------------------------
  // TODO 1: Hadamard gate.
  // Matrix (unnormalized): [[1, 1], [1, -1]], then scale by 1/sqrt(2).
  // Call this.applyMatrix(matrix, 'H') with your matrix.
  H() {
    // your code here
  }

  // -----------------------------------------------------------------
  // TODO 2: Pauli-X gate (the quantum NOT — swaps |0> and |1>).
  // Matrix: [[0, 1], [1, 0]]
  X() {
    // your code here
  }

  // -----------------------------------------------------------------
  // TODO 3: Pauli-Y gate.
  // Matrix: [[0, -i], [i, 0]]  — remember C.make(re, im) for complex entries.
  Y() {
    // your code here
  }

  // -----------------------------------------------------------------
  // TODO 4: Pauli-Z gate.
  // Matrix: [[1, 0], [0, -1]]
  Z() {
    // your code here
  }

  // -----------------------------------------------------------------
  // TODO 5 (bonus): RY(theta) — rotation about the Bloch sphere's Y axis.
  // Matrix: [[cos(theta/2), -sin(theta/2)], [sin(theta/2), cos(theta/2)]]
  // theta is in RADIANS. This is what you'll use for the 75/25 bonus —
  // solve cos^2(theta/2) = 0.75 for theta, then check your slider matches.
  RY(theta) {
    // your code here
  }

  // -----------------------------------------------------------------
  // TODO 6: probability of measuring 0.
  // Born's rule: P(0) = |a|^2. There's a C.abs2() helper for this.
  prob0() {
    // your code here — replace the next line
    return 0.5;
  }

  // -----------------------------------------------------------------
  // TODO 7: probability of measuring 1.
  // Either |b|^2 directly, or just 1 - prob0().
  prob1() {
    // your code here — replace the next line
    return 0.5;
  }

  /** Given — Bloch sphere angles, once prob0/prob1 exist this "just works". */
  bloch() {
    const theta = 2 * Math.acos(Math.min(1, Math.max(-1, Math.sqrt(this.prob0()))));
    const phi = (C.abs(this.b) < 1e-9) ? 0 : (C.arg(this.b) - C.arg(this.a));
    return { theta, phi };
  }

  // -----------------------------------------------------------------
  // TODO 8: sample N independent measurement shots WITHOUT collapsing
  // the qubit (so clicking "run shots" repeatedly on the same state
  // gives fresh statistics each time, like the real Problem 1 asks for).
  //
  // For each of the n shots: draw a random number in [0,1) and compare
  // it to prob0() to decide if that shot came out 0 or 1. Return the
  // counts, e.g. { c0: 512, c1: 488, p0: 0.5, p1: 0.5 }.
  sampleShots(n) {
    // your code here — replace the next line
    return { c0: n / 2, c1: n / 2, p0: 0.5, p1: 0.5 };
  }

  /** Given — single projective measurement that collapses the state.
   *  Not required for Problem 1's histogram, but useful for Problem 2
   *  style single-shot demos if you want to extend this later. */
  measure() {
    const p0 = this.prob0();
    const result = Math.random() < p0 ? 0 : 1;
    this.a = result === 0 ? C.make(1, 0) : C.make(0, 0);
    this.b = result === 0 ? C.make(0, 0) : C.make(1, 0);
    return result;
  }
}
