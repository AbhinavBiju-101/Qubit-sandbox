# Qubit Sandbox (Flask)

Same site as before, restructured as a small Flask app instead of raw
static HTML — one `app.py` you run with `python`, no npm, no build step,
no framework concepts beyond "a route returns a page."

## Project layout

```
qubit-flask/
├── app.py                  ← run this
├── requirements.txt
├── templates/               ← the 5 pages (Flask/Jinja HTML)
│   ├── index.html
│   ├── single-qubit.html
│   ├── two-qubit.html
│   ├── physical-qubit.html
│   └── reality-check.html
└── static/
    ├── css/style.css
    └── js/
        ├── quantum.js       ← single-qubit complex-number engine
        ├── twoqubit.js      ← two-qubit state engine
        ├── bloch.js         ← Bloch sphere SVG renderer
        └── chrome.js        ← shared nav/footer, injected on every page
```

Flask's only two jobs here are: (1) match a URL like `/single-qubit` to a
template, and (2) serve everything under `static/` at `/static/...`. All
the actual quantum logic still runs in the browser in JavaScript — the
Python side is just a page router.

## Running it

```bash
pip install -r requirements.txt
python app.py
```

Then open **http://localhost:5000** in a browser. `app.py` runs with
`debug=True`, so editing any template or static file and refreshing the
page picks up the change immediately — no restart needed while you're
developing.

## Pages / routes

| Route              | Template                | Problem | What it does |
|---------------------|--------------------------|---------|---------------|
| `/`                 | `index.html`             | —       | Landing page, live mini-demo |
| `/single-qubit`     | `single-qubit.html`      | 1       | Bloch sphere, gates, 1000-shot histogram, 75/25 bonus |
| `/two-qubit`        | `two-qubit.html`         | 2       | Prepare/measure `|00⟩..|11⟩`, Bell-state entanglement bonus |
| `/physical-qubit`   | `physical-qubit.html`    | 3       | Hardware chain diagram + live decoherence/temperature demo |
| `/reality-check`    | `reality-check.html`     | 5       | Real qubit-count stats, system architecture, scaling bottleneck |

## Deploying

This is a real (if tiny) Flask app now, so it deploys anywhere Python
apps do:

- **Render / Railway / Fly.io** — point them at this repo, they detect
  Flask automatically or via a `Procfile` (`web: python app.py`, or
  better, `web: gunicorn app:app` for production).
- **PythonAnywhere** — upload the folder, point their WSGI config at `app`.
- Before any real deployment, install a production server instead of the
  Flask dev server:
  ```bash
  pip install gunicorn
  gunicorn app:app
  ```
  and turn `debug=False` in `app.py` — the built-in server explicitly
  warns it isn't meant for production traffic.

## Verified working

Every route (`/`, `/single-qubit`, `/two-qubit`, `/physical-qubit`,
`/reality-check`) and every static asset (`style.css`, all four `.js`
files) was hit with `curl` against a running instance of this app and
returned `200 OK` before this was packaged — this isn't just "should
work," it was actually run.

## Notes on the "Reality Check" numbers

Qubit counts and fidelities in `reality-check.html` reflect publicly
reported figures at time of writing and will go stale — that's called
out on the page itself. Update before a live judging demo if it's been
more than a few weeks.
