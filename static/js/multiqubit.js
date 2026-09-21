/* ===================================================================
   multiqubit.js — a small, real N-qubit state-vector engine, built on
   the same C complex-number helper as quantum.js/twoqubit.js. Needed
   once lessons go past 2 qubits (teleportation's 3, the bit-flip
   code's 5 with ancillas) — everything here is literal amplitude
   bookkeeping over a 2^n-dimensional array, nothing precomputed.

   Qubit indexing: qubit 0 is the MOST significant bit of the basis
   index, matching the usual |q0 q1 q2...⟩ reading order.
=================================================================== */

class MultiQubit {
  constructor(n) {
    this.n = n;
    this.dim = 1 << n;
    this.reset();
  }

  reset() {
    this.amps = new Array(this.dim);
    for (let i = 0; i < this.dim; i++) this.amps[i] = C.make(0);
    this.amps[0] = C.make(1);
  }

  _bit(i, q) { return (i >> (this.n - 1 - q)) & 1; }
  _flip(i, q) { return i ^ (1 << (this.n - 1 - q)); }

  /** Apply a 2x2 complex matrix to qubit q. */
  applyGate1(q, m) {
    const out = this.amps.slice();
    for (let i = 0; i < this.dim; i++) {
      if (this._bit(i, q) === 0) {
        const j = this._flip(i, q);
        const a0 = this.amps[i], a1 = this.amps[j];
        out[i] = C.add(C.mul(m[0][0], a0), C.mul(m[0][1], a1));
        out[j] = C.add(C.mul(m[1][0], a0), C.mul(m[1][1], a1));
      }
    }
    this.amps = out;
  }

  H(q) { const s = 1/Math.sqrt(2); this.applyGate1(q, [[C.make(s), C.make(s)], [C.make(s), C.make(-s)]]); }
  X(q) { this.applyGate1(q, [[C.make(0), C.make(1)], [C.make(1), C.make(0)]]); }
  Y(q) { this.applyGate1(q, [[C.make(0), C.make(0,-1)], [C.make(0,1), C.make(0)]]); }
  Z(q) { this.applyGate1(q, [[C.make(1), C.make(0)], [C.make(0), C.make(-1)]]); }

  /** CNOT with the given control/target qubit indices. */
  CNOT(control, target) {
    const out = this.amps.slice();
    for (let i = 0; i < this.dim; i++) {
      if (this._bit(i, control) === 1 && this._bit(i, target) === 0) {
        const j = this._flip(i, target);
        out[i] = this.amps[j];
        out[j] = this.amps[i];
      }
    }
    this.amps = out;
  }

  /** Projective measurement of one qubit in the Z basis. Collapses
   *  and renormalizes the whole register (a real partial measurement,
   *  not a shortcut) and returns 0 or 1. */
  measureQubit(q) {
    let p0 = 0;
    for (let i = 0; i < this.dim; i++) if (this._bit(i, q) === 0) p0 += C.abs2(this.amps[i]);
    const outcome = Math.random() < p0 ? 0 : 1;
    let norm = 0;
    for (let i = 0; i < this.dim; i++) {
      if (this._bit(i, q) !== outcome) this.amps[i] = C.make(0);
      else norm += C.abs2(this.amps[i]);
    }
    const scale = norm > 1e-12 ? 1/Math.sqrt(norm) : 0;
    for (let i = 0; i < this.dim; i++) this.amps[i] = C.scale(this.amps[i], scale);
    return outcome;
  }

  /** |amp|^2 for every basis state, in index order. */
  probabilities() { return this.amps.map(a => C.abs2(a)); }

  /** Grover: flip the sign of one basis state's amplitude. */
  markPhase(index) { this.amps[index] = C.scale(this.amps[index], -1); }

  /** Grover: reflect every amplitude about the register's mean
   *  amplitude — the diffusion operator, 2|s⟩⟨s| − I, for a register
   *  that started in the uniform superposition. */
  diffusionAboutMean() {
    let meanRe = 0, meanIm = 0;
    for (const a of this.amps) { meanRe += a.re; meanIm += a.im; }
    meanRe /= this.dim; meanIm /= this.dim;
    this.amps = this.amps.map(a => ({ re: 2*meanRe - a.re, im: 2*meanIm - a.im }));
  }

  /** Binary string label for a basis index, e.g. 5 (n=3) -> "101". */
  static label(index, n) { return index.toString(2).padStart(n, '0'); }
}
