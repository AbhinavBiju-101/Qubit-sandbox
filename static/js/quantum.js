/* ===================================================================
   quantum.js — minimal complex-number + single-qubit state engine.
   No dependencies. This is the real math (not a stand-in): a qubit
   state is stored as two complex amplitudes [alpha, beta] for
   |0> and |1>, and gates are literal 2x2 unitary matrices.
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

/** A single-qubit pure state, amplitudes for |0> and |1>. */
class Qubit {
  constructor() {
    this.a = C.make(1, 0); // amplitude of |0>
    this.b = C.make(0, 0); // amplitude of |1>
    this.log = [];
  }

  /** Apply a 2x2 matrix [[m00,m01],[m10,m11]] of complex entries. */
  applyMatrix(m, label) {
    const a2 = C.add(C.mul(m[0][0], this.a), C.mul(m[0][1], this.b));
    const b2 = C.add(C.mul(m[1][0], this.a), C.mul(m[1][1], this.b));
    this.a = a2; this.b = b2;
    this.normalize();
    if (label) this.log.push(label);
    return this;
  }

  normalize() {
    const n = Math.sqrt(C.abs2(this.a) + C.abs2(this.b));
    if (n > 1e-12) { this.a = C.scale(this.a, 1 / n); this.b = C.scale(this.b, 1 / n); }
  }

  H() {
    const s = SQRT1_2;
    return this.applyMatrix([
      [C.make(s), C.make(s)],
      [C.make(s), C.make(-s)]
    ], 'H');
  }

  X() {
    return this.applyMatrix([
      [C.make(0), C.make(1)],
      [C.make(1), C.make(0)]
    ], 'X');
  }

  Y() {
    return this.applyMatrix([
      [C.make(0), C.make(0, -1)],
      [C.make(0, 1), C.make(0)]
    ], 'Y');
  }

  Z() {
    return this.applyMatrix([
      [C.make(1), C.make(0)],
      [C.make(0), C.make(-1)]
    ], 'Z');
  }

  /** Rotation about Y axis of the Bloch sphere by angle theta (radians). */
  RY(theta) {
    const c = Math.cos(theta / 2), s = Math.sin(theta / 2);
    return this.applyMatrix([
      [C.make(c), C.make(-s)],
      [C.make(s), C.make(c)]
    ], `RY(${(theta * 180 / Math.PI).toFixed(1)}°)`);
  }

  reset() { this.a = C.make(1, 0); this.b = C.make(0, 0); this.log = []; return this; }

  /** Probability of measuring 0 / 1. */
  prob0() { return C.abs2(this.a); }
  prob1() { return C.abs2(this.b); }

  /** Bloch sphere angles: theta from north pole (|0>), phi azimuthal. */
  bloch() {
    const theta = 2 * Math.acos(Math.min(1, Math.max(-1, C.abs(this.a))));
    const phi = (C.abs(this.b) < 1e-9) ? 0 : (C.arg(this.b) - C.arg(this.a));
    return { theta, phi };
  }

  /** Simulate one projective measurement in the computational basis. Collapses state. */
  measure() {
    const p0 = this.prob0();
    const result = Math.random() < p0 ? 0 : 1;
    this.a = result === 0 ? C.make(1, 0) : C.make(0, 0);
    this.b = result === 0 ? C.make(0, 0) : C.make(1, 0);
    return result;
  }

  /** Sample N measurement outcomes WITHOUT collapsing the working state
   *  (used for the "run N shots" histograms — each shot is independent). */
  sampleShots(n) {
    const p0 = this.prob0();
    let c0 = 0, c1 = 0;
    for (let i = 0; i < n; i++) { if (Math.random() < p0) c0++; else c1++; }
    return { c0, c1, p0, p1: 1 - p0 };
  }
}
