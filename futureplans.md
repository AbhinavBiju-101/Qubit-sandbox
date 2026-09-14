# Future Plans

Everything below was discussed but deliberately **not** built for the
today-9pm deadline, so the core app (Dashboard, Single Qubit lesson,
Two Qubit / Physical Qubit / Reality Check sandboxes, Docker + deploy)
could actually ship. Nothing here is started except where noted.

---

## 1. Hardware Lab — full build-out

`templates/hardware-lab.html` and the `/hardware-lab` route exist and
are wired into the sidebar (badge: "Soon"), but the content is just
TODO placeholders. Planned sections, in the order discussed:

- **Transistor structure** — cross-section diagram of a MOSFET
  (gate/source/drain/substrate) as the classical baseline.
- **Superconducting circuit layout** — an actual chip-layout-style
  diagram (capacitor pads, Josephson junction placement, coplanar
  waveguide routing), one level more detailed than the labeled-box
  diagram already on the Physical Qubit page.
- **LC oscillation / zero-resistance analogy** — an animated classical
  LC tank circuit (charge sloshing between capacitor and inductor
  forever, no resistance = no energy loss) as a bridge into why a
  Josephson junction behaves like a "nonlinear inductor with zero
  resistance."

You mentioned wanting to research and build part of this yourself —
the route/template/sidebar plumbing is ready specifically so you can
drop content straight in without touching `app.py` again.

## 2. ~~Course-ify Two Qubit / Physical Qubit / Reality Check~~ — DONE

All four lessons (Single Qubit, Two Qubits, Physical Qubit, Reality
Check) now use the `.lesson-step` + progress-bar format, each calling
`initLessonProgress('<lesson-id>')`. The Dashboard reads real
per-lesson progress via `getLessonProgress()` for all four and shows
a "completed lessons" count (100% on a lesson = completed). Step
counts: Single Qubit 4, Two Qubits 3, Physical Qubit 4, Reality Check
4 — `dashboard.html`'s `LESSONS` array is the single place that needs
updating if step counts change.

## 3. Dedicated Sandbox page ("open in IDE" pattern)

The idea: each lesson has a small embedded demo, but a separate full
`/sandbox` page would let you pick any concept (single qubit, two
qubit, etc.) and get the interactive widget full-screen with no lesson
scaffolding around it — closer to a W3Schools/GeeksforGeeks "Try it
yourself" popout. Not built. Would need:

- A `/sandbox/<topic>` route
- Reuse of the existing widget code (quantum.js/twoqubit.js/bloch.js
  already don't depend on the lesson markup, so this is mostly a new
  template + route, not new logic)
- An "Open in Sandbox" button added to each lesson step

## 4. Introductory Quantum Mechanics lesson (Lesson 0)

Covering, before Single Qubit: state vectors, Hilbert space, the wave
function, and probability amplitude — the formalism the Single Qubit
lesson currently just asserts ("a qubit's state is a pair of complex
numbers..."). Would sit as `/qm-basics`, presumably first in the
sidebar/dashboard ordering, marked Lesson 0.

## 5. Simulation vs. real hardware (Qiskit Aer comparison)

Discussed goal: run the same circuit two ways — this app's own
from-scratch complex-matrix simulator, and IBM's `qiskit-aer` — and
compare the statistical noise between them, as a concrete "how good is
our toy simulator, actually" check. This requires a Python backend
endpoint (Flask route calling into `qiskit`), not just client-side JS,
since Qiskit isn't a JS library. Rough shape:

```python
# sketch only — not implemented
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator

@app.route("/api/compare-shots")
def compare_shots():
    qc = QuantumCircuit(1, 1)
    qc.h(0)
    qc.measure(0, 0)
    result = AerSimulator().run(qc, shots=1000).result()
    return result.get_counts()
```

Would need `qiskit` + `qiskit-aer` added to `requirements.txt` (they're
sizeable dependencies — worth checking Docker image size impact before
adding), plus a frontend panel on the Single Qubit lesson showing
"your sandbox" counts next to "Qiskit Aer" counts side by side.

## 6. App walkthrough / onboarding tutorial

As the app grows, a short guided tour of the app itself (not the
physics) — "here's the sidebar, here's how lessons track progress,
here's the dashboard" — for first-time visitors. Not started. Could be
a simple dismissible overlay on first visit to `/dashboard`, gated on
a `localStorage` flag similar to the existing progress tracking.

## 7. Real photography / high-res imagery

You asked for a more "professional" look with real images, not just
diagrams. This build could only ship hand-built SVG illustrations and
diagrams — there's no network access in the build environment to fetch
real photographs, and fabricating "photos" would be dishonest about
what they are. To add real imagery later:

- Drop licensed/royalty-free photos (dilution refrigerator interiors,
  actual chip photos — many are published openly by IBM/Google/Rigetti
  research blogs, check individual licensing) into `static/images/`.
- Reference them normally: `<img src="{{ url_for('static', filename='images/dilution-fridge.jpg') }}">`.
- Good candidates: hero image on `landing.html`, a real chip photo
  alongside the schematic on `physical-qubit.html`.

## 8. Qiskit real-hardware toggle (from earlier brainstorm)

Originally discussed as "Branch B" — running the Single/Two Qubit
sandboxes against real IBM Quantum hardware via the IBM Quantum API,
with a toggle between "Simulated" and "Real hardware run," to make the
"real-world constraints" theme concrete (showing real hardware noise
vs. the idealized simulator). Requires an IBM Quantum API key, network
calls from the Flask backend, and realistically a job-queue/polling UI
since real hardware runs aren't instant. Bigger lift than #5 — probably
sequence after it.

## 9. PWA / installable app, embeddable widget

From the very first design pass: a Progressive Web App manifest so the
site installs to a phone home screen, and/or an embeddable version of
a single widget (e.g. the Bloch sphere) for dropping into course pages
or Notion docs. Neither started.

---

## Suggested order if picking this back up

1. Course-ify the remaining three lessons (#2) — cheapest, reuses
   existing code, most directly finishes what's already started.
2. Hardware Lab content (#1) — you're doing the research yourself,
   plumbing is ready whenever you are.
3. Lesson 0 / QM basics (#4) — natural prerequisite once you're adding
   more lessons anyway.
4. Qiskit Aer comparison (#5) — the most technically distinctive
   feature for a hackathon judge, but the biggest new dependency.
5. Everything else (#3, #6, #7, #8, #9) as time allows.
