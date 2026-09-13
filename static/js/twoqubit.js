/* ===================================================================
   twoqubit.js — minimal 2-qubit state engine. State is 4 complex
   amplitudes indexed 00,01,10,11 (qubit1 qubit2). Real gate matrices,
   not lookup tables: X1, X2, H1, and CNOT(control=1, target=2).
=================================================================== */

class TwoQubit {
  constructor() {
    this.amp = [C.make(1, 0), C.make(0, 0), C.make(0, 0), C.make(0, 0)]; // |00>
    this.gateCount = 0;
    this.log = [];
  }

  reset() { this.amp = [C.make(1,0), C.make(0,0), C.make(0,0), C.make(0,0)]; this.gateCount = 0; this.log = []; return this; }

  X1() { // flip qubit 1: 00<->10, 01<->11
    const a = this.amp;
    this.amp = [a[2], a[3], a[0], a[1]];
    this.gateCount++; this.log.push('X(q1)');
    return this;
  }
  X2() { // flip qubit 2: 00<->01, 10<->11
    const a = this.amp;
    this.amp = [a[1], a[0], a[3], a[2]];
    this.gateCount++; this.log.push('X(q2)');
    return this;
  }
  H1() { // Hadamard on qubit 1
    const s = SQRT1_2, a = this.amp;
    const n00 = C.scale(C.add(a[0], a[2]), s);
    const n01 = C.scale(C.add(a[1], a[3]), s);
    const n10 = C.scale(C.add(a[0], C.scale(a[2], -1)), s);
    const n11 = C.scale(C.add(a[1], C.scale(a[3], -1)), s);
    this.amp = [n00, n01, n10, n11];
    this.gateCount++; this.log.push('H(q1)');
    return this;
  }
  CNOT() { // control q1, target q2: swap 10<->11
    const a = this.amp;
    this.amp = [a[0], a[1], a[3], a[2]];
    this.gateCount++; this.log.push('CNOT(q1→q2)');
    return this;
  }

  probs() { return this.amp.map(a => C.abs2(a)); }

  /** Minimum X-gate recipe (from |00>) to prepare a target computational basis state. */
  static minGatesFor(target) {
    const gates = [];
    if (target[0] === '1') gates.push('X(q1)');
    if (target[1] === '1') gates.push('X(q2)');
    return gates;
  }

  /** Sample N shots, returns counts for '00','01','10','11'. */
  sampleShots(n) {
    const p = this.probs();
    const cum = [p[0], p[0]+p[1], p[0]+p[1]+p[2], 1];
    const labels = ['00','01','10','11'];
    const counts = {'00':0,'01':0,'10':0,'11':0};
    for (let i = 0; i < n; i++) {
      const r = Math.random();
      let idx = cum.findIndex(c => r <= c);
      if (idx === -1) idx = 3;
      counts[labels[idx]]++;
    }
    return counts;
  }

  measure() {
    const p = this.probs();
    const r = Math.random();
    const cum = [p[0], p[0]+p[1], p[0]+p[1]+p[2], 1];
    let idx = cum.findIndex(c => r <= c);
    if (idx === -1) idx = 3;
    const labels = ['00','01','10','11'];
    return labels[idx];
  }
}
