# Qubit Sandbox

A small Flask web app for a quantum computing hackathon problem set —
built as lessons with live, real-math sandboxes instead of static
write-ups.

Live pages: an introduction/landing page, a dashboard, a step-by-step
**Single Qubit** lesson (superposition, gates, 1,000-shot measurement,
the 75/25 bonus), plus **Two Qubits**, **Physical Qubit**, and
**Reality Check** sandboxes. A **Hardware Lab** page is scaffolded and
intentionally left as a stub — see `futureplans.md`.

---

## Quick start

```bash
pip install -r requirements.txt
python app.py
```

Open **http://localhost:5000**. `debug=True` is on in `app.py`, so
editing a template or static file and refreshing picks up the change
immediately — no restart needed.

## Or run it in Docker

```bash
docker build -t qubit-sandbox .
docker run -p 5000:5000 qubit-sandbox
```

Open **http://localhost:5000**. The container runs `gunicorn` (a real
WSGI server), not Flask's dev server — that's the difference between
this and the local `python app.py` run.

---

## Project structure

```
qubit-flask/
├── app.py                     ← routes + sidebar nav data (NAV_ITEMS)
├── requirements.txt
├── Dockerfile
├── .dockerignore
├── .gitignore
├── futureplans.md             ← everything discussed but deferred
├── challenge/                 ← standalone self-implementation practice (see below)
│   ├── index.html
│   ├── quantum-challenge.js   ← stub with TODOs — fill this in yourself
│   ├── bloch.js               ← rendering only, given as-is
│   ├── style.css
│   └── CHALLENGE.md
├── templates/
│   ├── base.html              ← sidebar app-shell, extended by every page below
│   ├── landing.html           ← standalone marketing/intro page, NO sidebar
│   ├── dashboard.html         ← overview hub, lesson cards, live stats
│   ├── single-qubit.html      ← Lesson 1, full step-by-step format
│   ├── two-qubit.html
│   ├── physical-qubit.html
│   ├── hardware-lab.html      ← stub, "Coming soon"
│   └── reality-check.html
└── static/
    ├── css/style.css          ← the entire design system, one file
    └── js/
        ├── quantum.js         ← single-qubit complex-number engine (the real math)
        ├── twoqubit.js        ← two-qubit state engine
        ├── bloch.js           ← Bloch sphere SVG renderer
        ├── sidebar.js         ← collapse/expand + mobile drawer
        ├── lesson-progress.js ← generic step-checkbox progress tracker
        └── stats.js           ← localStorage usage counters (shots run, gates applied)
```

## How pages are wired together

`app.py` defines `NAV_ITEMS` once — a list of dicts (label, route,
icon name) — and injects it into every template via a
`@app.context_processor`. `templates/base.html` loops over that list
to build the sidebar, so **adding a new lab page later is: add a
route in `app.py`, add one entry to `NAV_ITEMS`, create the
template** — the sidebar updates itself, nothing else to touch.

Every page except `landing.html` does `{% extends "base.html" %}` and
fills in `{% block content %}` / `{% block scripts %}`. The landing
page is intentionally standalone (its own `<html>`, own nav bar) since
it's a different layout family (marketing page, not an app screen).

## The lesson / progress system

`single-qubit.html` is the reference implementation of the lesson
format:

- Sections are wrapped in `.lesson-step` divs, each with a
  `data-step-check="stepN"` checkbox.
- `static/js/lesson-progress.js` (`initLessonProgress('single-qubit')`)
  reads/writes which steps are checked to `localStorage`, and drives
  the progress bar (`#lp-fill` / `#lp-pct`) automatically.
- `dashboard.html` calls `getLessonProgress('single-qubit', 4)` to
  show the same percentage on the lesson card, without duplicating
  any state.

This pattern isn't applied to Two Qubits / Physical Qubit / Reality
Check yet — see `futureplans.md` §2 for exactly what's left to do
there.

## The quantum "simulation" is real math

`static/js/quantum.js` implements actual complex numbers and 2×2
unitary matrices (H, X, Y, Z, RY(θ)) applied to real amplitude pairs
`[α, β]`. `static/js/twoqubit.js` does the same for a 4-amplitude
two-qubit state with X1, X2, H1, and CNOT. Measurement sampling uses
`Math.random()` weighted by `|amplitude|²` — Born's rule, not a
lookup table.

## The `challenge/` folder

A **standalone, self-contained** copy of the Single Qubit sandbox
where the actual physics (`quantum-challenge.js`) is left as TODOs —
built so you can implement the gate matrices and measurement logic
yourself without looking at the finished `static/js/quantum.js`. It
doesn't run through Flask at all; just open `challenge/index.html`
directly in a browser. Instructions and hints are in
`challenge/CHALLENGE.md`. This folder is excluded from the Docker
image (see `.dockerignore`) since it's a practice exercise, not part
of the deployed app.

## Deploying beyond Docker

Since this is a real (if small) Flask app, it deploys anywhere Python
apps do:

- **Render / Railway / Fly.io** — point them at the repo; most detect
  Flask automatically, or use the included `Dockerfile` directly.
- **A VPS** — `pip install -r requirements.txt`, then
  `gunicorn --bind 0.0.0.0:5000 app:app` behind nginx.
- Whatever you use, make sure `debug=False` (or just run via gunicorn,
  which never uses Flask's debug server) before it's public — the
  built-in dev server explicitly warns it isn't meant for production
  traffic.

## Known limitations, honestly

- **No real photographs.** You asked for a more "professional" look
  with high-res images. Everything visual here is a hand-built SVG
  illustration/diagram — there's no network access in the environment
  this was built in to fetch real photos, and fabricating placeholder
  "photos" would misrepresent what they are. `futureplans.md` §7 has
  notes on where to drop real images in once you have some.
- **Reality Check's hardware numbers** are publicly reported figures
  current as of when this was built and will go stale — worth a
  quick check before any live demo more than a few weeks out.
- **Only Single Qubit is a full lesson.** The other three pages work
  and are reskinned, but don't have the step/progress format yet.

See `futureplans.md` for the complete list of deferred ideas (Hardware
Lab content, Qiskit Aer comparison, an intro QM lesson, a dedicated
sandbox page, PWA support, and more) with enough detail to pick each
one back up later.
