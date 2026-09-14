# Challenge: Build the Coin-Flip Demo Yourself

This is Hackathon Problem 1, stripped down so you implement the actual
quantum logic. Open `index.html` in a browser — the buttons and layout
are already wired up and identical to the real Single Qubit lesson.
Nothing will respond correctly until you fill in `quantum-challenge.js`.

**Don't open `../static/js/quantum.js`** — that's the finished
reference implementation. Solve it yourself first, compare after.

## What's already done for you

- `bloch.js` — draws the state vector on the sphere. Not part of the
  physics, just rendering; don't worry about it.
- `applyMatrix()` and `normalize()` in `Qubit` — the generic "multiply
  the state by this 2×2 matrix" machinery.
- `measure()` — a single collapsing measurement (given as an example
  of how `prob0()` gets used once you've implemented it).
- The `C` object — complex number helpers: `C.make(re, im)`,
  `C.add`, `C.mul`, `C.abs2`, etc.

## What you need to implement (in order)

1. **`H()`** — Hadamard gate. Matrix: `1/√2 × [[1, 1], [1, -1]]`.
2. **`X()`** — Pauli-X (bit flip). Matrix: `[[0, 1], [1, 0]]`.
3. **`Y()`** — Pauli-Y. Matrix: `[[0, -i], [i, 0]]`. Use
   `C.make(0, -1)` for `-i`.
4. **`Z()`** — Pauli-Z (phase flip). Matrix: `[[1, 0], [0, -1]]`.
5. **`RY(theta)`** (bonus) — rotation by angle `theta` (radians)
   about the Bloch sphere's Y axis. Matrix:
   ```
   [[cos(θ/2), -sin(θ/2)],
    [sin(θ/2),  cos(θ/2)]]
   ```
6. **`prob0()`** — Born's rule: `P(0) = |α|²`. Use `C.abs2(this.a)`.
7. **`prob1()`** — `P(1) = |β|²`, or just `1 - this.prob0()`.
8. **`sampleShots(n)`** — run `n` independent simulated measurements
   *without* collapsing the working state (so you can click "run
   shots" repeatedly on the same prepared state and get fresh
   statistics each time — that's what the real hackathon problem
   asks for: "run the circuit multiple times"). For each shot, draw
   `Math.random()` and compare it against `prob0()`.

## Checkpoints to verify you're right

- Fresh `Qubit()`, no gates: `prob0()` should be exactly `1`.
- After `X()`: `prob0()` should be exactly `0`.
- After `H()`: `prob0()` should be `0.5` (and running 1000 shots
  should land close to a 500/500 split, not exact).
- After `Z()` alone (starting from `|0⟩`): should look identical to
  no gate at all on the Bloch sphere — Z only affects the *phase*,
  and phase is invisible when you're sitting at the north pole.
  If you apply `H()` then `Z()`, *that* should visibly move the
  vector to the opposite side of the equator from `H()` alone.
- For the bonus: `RY(θ)` with `θ ≈ 60°` (in radians:
  `60 * Math.PI / 180`) should give `prob0() ≈ 0.75`.

## If you get stuck

The formula for the bonus angle: you need
`cos²(θ/2) = 0.75`, so `θ = 2 · arccos(√0.75)`. Compute that in a
console (`2 * Math.acos(Math.sqrt(0.75)) * 180 / Math.PI`) to check
your slider math lines up with your `RY()` implementation.
