# Qubit Sandbox

A small Flask web app for a quantum computing hackathon problem set —
built as lessons with live, real-math sandboxes instead of static
write-ups.

Live pages: a landing page, a personalized **Dashboard**, a full
**Lessons** catalog (QM Basics → Single Qubit → Two Qubits → Physical
Qubit → Hardware Lab → Reality Check, plus any published **community
lessons**, with prev/next navigation through the whole sequence), a
**Demos** hub for the hackathon showcase (Coin Flip + Single Qubit, no
sign-in needed), a full-screen **Sandbox**, a **Python IDE** with a
real (AST-restricted, not arbitrary-exec) code editor plus runnable
Qiskit snippets, a **Lesson Creator** workspace for verified creator
accounts (create, edit, publish/unpublish, delete), and an **Account**
page (profile, stats, per-lesson progress, account deletion). **Sign-
in is real** — Google OAuth + server sessions, backed by SQLite, with
separate **Sign in** (`/login`) and **Create account** (`/signup`,
picks student/educator/creator) flows — see "Accounts" below.

---

## Quick start

```bash
pip install -r requirements.txt
python app.py
```

Open **http://localhost:5000**. `debug=True` is on in `app.py`, so
editing a template or static file and refreshing picks up the change
immediately — no restart needed.

`qiskit` + `qiskit-aer` are in `requirements.txt` and power
`/api/compare-shots` (used by Single Qubit's Step 5 and the Python
IDE). They're imported lazily in `app.py`, so the rest of the app still
runs even if they're not installed — that one endpoint just returns a
501 with a clear message instead.

Sign-in works out of the box with no setup — click "Continue as Demo
Guest" on `/login` for a real (if not Google-verified) account
immediately. See "Accounts" below to wire up real Google sign-in.

## Or run it in Docker

```bash
docker build -t qubit-sandbox .
docker run -p 5000:5000 qubit-sandbox
```

Open **http://localhost:5000**. The container runs `gunicorn` (a real
WSGI server), not Flask's dev server. `qiskit-aer` adds real weight to
the image — check size before deploying somewhere with a tight limit.

---

## Project structure

```
qubit-flask/
├── app.py                     ← routes + nav data (NAV_ITEMS) + OAuth/session wiring + API
├── db.py                      ← SQLite: users (account_type/creator_status), lesson progress, custom_lessons
├── requirements.txt
├── Dockerfile
├── .dockerignore
├── .gitignore
├── .env.example                ← SECRET_KEY / GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / CREATOR_EMAILS / ADMIN_EMAILS
├── instance/                   ← gitignored; qubit_sandbox.db (SQLite) lives here, created on first run
├── futureplans.md             ← what's shipped, what's deferred, in detail
├── challenge/                 ← standalone self-implementation practice (see below)
│   ├── index.html
│   ├── quantum-challenge.js   ← stub with TODOs — fill this in yourself
│   ├── bloch.js               ← rendering only, given as-is
│   ├── style.css
│   └── CHALLENGE.md
├── templates/
│   ├── base.html              ← sidebar app-shell, extended by every page below
│   ├── landing.html           ← standalone marketing/intro page, NO sidebar
│   ├── login.html             ← standalone sign-in page (returning users), NO sidebar
│   ├── signup.html            ← standalone create-account page (student/educator/creator picker), NO sidebar
│   ├── _lesson_nav.html       ← Jinja macro: prev/next lesson nav, included by every lesson template
│   ├── dashboard.html         ← personalized: onboarding panel, stats, "continue where you left off"
│   ├── lessons.html           ← full lesson catalog + community lessons section
│   ├── account.html           ← @login_required: real profile, stats, per-lesson progress, danger zone
│   ├── admin-creators.html    ← @login_required + ADMIN_EMAILS: approve/reject pending creator requests
│   ├── demos.html             ← open-access hub: Demo 1 (Coin Flip) + Single Qubit
│   ├── demo-coin-flip.html    ← Demo 1, a working scaffold (live widgets, sparse narrative on purpose)
│   ├── sandbox.html           ← full-screen widgets, no lesson scaffolding, hash deep-links
│   ├── qm-basics.html         ← Lesson 0, open access
│   ├── single-qubit.html      ← Lesson 1, open access, full step-by-step format
│   ├── two-qubit.html         ← Lesson 2, gated
│   ├── physical-qubit.html    ← Lesson 3, gated
│   ├── hardware-lab.html      ← Lesson 4, gated — MOSFET diagram, LC-loop demo, chip-layout diagram
│   ├── reality-check.html     ← Lesson 5, gated
│   ├── lesson-creator.html    ← real authoring workspace for verified creators — create/edit/publish/delete
│   ├── custom-lesson.html     ← renders a published community lesson at /lessons/custom/<slug>
│   ├── python-ide.html        ← real AST-restricted code editor + runnable snippets + Circuit Builder
│   ├── embed-coin-flip.html   ← chrome-less, iframeable single-qubit widget (no sidebar)
│   └── embed-two-qubit.html   ← chrome-less, iframeable Bell-state widget (no sidebar)
└── static/
    ├── favicon.ico
    ├── manifest.json          ← PWA manifest
    ├── images/                ← logo.svg (the atom mark) + generated favicon/PWA icon sizes
    ├── css/style.css          ← the entire design system, one file
    └── js/
        ├── quantum.js         ← single-qubit complex-number engine (the real math)
        ├── twoqubit.js        ← two-qubit state engine
        ├── bloch.js           ← Bloch sphere SVG renderer
        ├── sidebar.js         ← collapse/expand + mobile drawer
        ├── lesson-progress.js ← step-checkbox progress tracker, backed by /api/progress (real accounts)
        ├── lessons-data.js    ← QS_LESSON_DEFS — the one place lesson id/title/href/step-count lives
        ├── stats.js           ← localStorage usage counters (shots run, gates applied)
        └── sw.js              ← PWA service worker (precaches app routes)
```

## How pages are wired together

`app.py` defines `NAV_ITEMS` once — a list of dicts (label, route, icon
name) — and injects it into every template via a
`@app.context_processor`. `templates/base.html` loops over that list to
build the sidebar: Dashboard, Lessons, Demos, Lesson Creator, Python
IDE, Account. **Individual lessons don't get their own sidebar row** —
they're reached through `/lessons` and `/demos` card links instead, so
the sidebar doesn't grow as more lessons get added.

Every page except `landing.html` and `login.html` does
`{% extends "base.html" %}` and fills in `{% block content %}` /
`{% block scripts %}`. Those two are intentionally standalone (own
`<html>`, own nav bar) — different layout family, not an app screen.

## Accounts

Real Google OAuth (via `Authlib`) + real server sessions (via
`Flask-Login`), backed by a small SQLite database (`db.py`: `users`,
`lesson_progress`, and `custom_lessons` tables, created automatically
in `instance/qubit_sandbox.db` on first run).

**Sign in vs. create account.** `/login` is for returning visitors —
Google or Demo Guest, straight through to wherever they were headed.
`/signup` is for new visitors: pick an account type first (Student,
Educator, or Creator — see below), then the same Google/Demo Guest
buttons, which apply the chosen type only if the resulting account is
freshly created (an existing account that lands on `/signup` by
mistake just signs in normally, keeping its original type).

**To enable real Google sign-in:**

1. Google Cloud Console → APIs & Services → Credentials → Create
   Credentials → OAuth client ID → Web application.
2. Authorized redirect URI: `http://localhost:5000/auth/google/callback`
   (swap host/port for your real domain when deploying).
3. Copy `.env.example` to `.env`, fill in `GOOGLE_CLIENT_ID` /
   `GOOGLE_CLIENT_SECRET` (and set a real `SECRET_KEY` — see the file
   for how). `app.py` auto-loads `.env` via `python-dotenv`.
4. Restart the app. `/login`/`/signup` now show a working "Continue
   with Google" button instead of a disabled one.

**Without those credentials set**, sign-in still works via "Continue
as Demo Guest" — a real account gets created (a real row in `users`,
a real session), just not Google-verified. Each click makes a
*fresh, isolated* guest identity rather than sharing one account
across visitors, so multiple people can demo this at once without
seeing each other's progress.

Routes marked `@login_required` in `app.py` (Two Qubits, Physical
Qubit, Hardware Lab, Reality Check, Account, `/admin/creators`)
actually redirect anonymous visitors to `/login?next=...` —
server-side, not a client-side hide (`curl` a gated route with no
cookie and you'll get a real `302`, not a `200` with hidden content).
QM Basics, Single Qubit, and everything under `/demos` / `/sandbox`
are never gated.

`window.QS_AUTHENTICATED` (set in `base.html` from Flask-Login's
`current_user`, server-truth) is the one place client-side JS checks
sign-in state — used by `lesson-progress.js` on the two open lessons,
where the progress UI should still adapt even though the page itself
isn't `@login_required`.

**Account types.** `users.account_type` is `'student'`, `'educator'`,
or `'creator'`, picked at signup (or requested later — see below).
Student and educator are instant and functionally similar today
(educator is currently just a profile label). **Creator** is
different — it also needs `creator_status` to reach `'verified'`
before `current_user.can_create_lessons` is true and
`/lesson-creator`'s authoring form unlocks:

- **`CREATOR_EMAILS`** env var (comma-separated) — a real,
  Google-verified sign-in with a matching email is verified instantly.
  Demo Guest accounts can request creator (to see what the pending
  state looks like) but can never auto-verify — there's no real email
  to check.
- Anyone else who requests creator access goes to `creator_status=
  'pending'` and needs a human. **`ADMIN_EMAILS`** env var
  (comma-separated) marks accounts that can see and act on pending
  requests at **`/admin/creators`** — real Approve/Reject buttons,
  backed by `db.set_creator_status()`. `current_user.is_admin` is
  computed from this env var at request time, not stored on the user
  row, so granting/revoking admin access is just an env var + restart.
- An existing student/educator account can request creator access
  after the fact too — not just at `/signup` — via a button on
  `/lesson-creator` (`POST /account/request-creator`).

**CSRF protection.** Every state-changing endpoint (`/api/progress/*`,
`/api/lessons*`, `/account/delete`, `/account/request-creator`,
`/admin/creators/*`) requires a matching `X-CSRF-Token` header — a
per-session token, set in `session['csrf_token']` on first request and
exposed to the frontend as `window.QS_CSRF_TOKEN` (a `<script>` block
in `base.html`). No `Flask-WTF` dependency; this is a small
hand-rolled double-submit check (`app.py`'s `csrf_protect` decorator).

**Account deletion.** The Account page has a "Danger zone" with a
real, irreversible delete — removes the user row, their lesson
progress, and any lessons they've published. `db.delete_user()`
handles the cascade manually since `PRAGMA foreign_keys = ON` is set
(SQLite won't enforce FK constraints without it, but won't let you
violate them once it's on either).

## Lesson Creator & community lessons

`/lesson-creator` shows one of several things depending on who's
looking: signed-out gets the pitch + a `/signup` link; signed-in
non-creators get a "request creator access" button; pending/rejected
creators get a status message; **verified creators** get a real
workspace:

- **Create**: title, short description, and up to 12 steps (each a
  title + plain-text body + an optional embedded widget, reusing
  `/embed/coin-flip`/`/embed/two-qubit` rather than building
  lesson-specific ones). `POST /api/lessons` validates everything
  server-side and writes to `custom_lessons` via
  `db.create_custom_lesson()`, which auto-generates a unique URL slug
  from the title (collisions get `-2`, `-3`, ... appended).
- **Edit, unpublish/republish, delete** your own lessons — `PUT`/
  `DELETE /api/lessons/<id>` and `POST /api/lessons/<id>/publish`, all
  checked server-side against `lesson.author_user_id` (a non-owner's
  attempt gets a real `403`). An unpublished lesson stays visible to
  its own author (to preview before republishing) but 404s for
  everyone else — same response as a nonexistent slug, so it doesn't
  leak that an unpublished lesson exists.

Published lessons render at `/lessons/custom/<slug>`
(`custom-lesson.html`) and appear in a "Community lessons" section on
`/lessons` — open to everyone, same as the built-in open lessons, no
sign-in needed to *read* one, though marking steps complete needs an
account like any other lesson (`initLessonProgress('custom-<slug>')`
— same checkboxes/progress bar as the built-in lessons, tracked under
a `custom-`-prefixed lesson id so it can't collide with the 6 fixed
ones). Step bodies are plain text only (Jinja autoescaping + CSS
`white-space: pre-line` for line breaks) — no HTML or markdown is
accepted or rendered anywhere in this feature, so there's no
stored-XSS surface despite this being user-submitted content shown to
every visitor. That progress isn't surfaced on Dashboard/Account yet
(both only know about the 6 built-in lesson ids) — see
`futureplans.md` #11 for what's left.

## The lesson / progress system

`single-qubit.html` is the reference implementation:

- Sections are wrapped in `.lesson-step` divs, each with a
  `data-step-check="stepN"` checkbox.
- `static/js/lesson-progress.js` (`initLessonProgress('single-qubit')`)
  POSTs which steps are checked to `/api/progress/<lesson_id>/step`
  (real, per-account, server-side — see "Accounts" above), drives the
  progress bar (`#lp-fill` / `#lp-pct`), and records a visit timestamp
  (`POST /api/progress/<lesson_id>/visit`) used by Dashboard's
  "Continue where you left off" list. All of this is a no-op (nothing
  saved, checkboxes disabled) when signed out — checked via
  `window.QS_AUTHENTICATED`, not by trying the API and failing.
- `static/js/lessons-data.js` holds `QS_LESSON_DEFS` — id, title, href,
  step count, gated flag — read by `dashboard.html`, `lessons.html`,
  and `account.html` so the list only needs updating in one place.

Every lesson (QM Basics, Single Qubit, Two Qubits, Physical Qubit,
Hardware Lab, Reality Check) uses this pattern now.

**Prev/Next navigation.** `LESSON_ORDER` + `_lesson_nav()` in `app.py`
define the canonical lesson sequence once; every lesson route passes
`prev_lesson`/`next_lesson` to a shared Jinja macro
(`templates/_lesson_nav.html`), rendered at the top and bottom of each
lesson page. Reordering `LESSON_ORDER` reorders the nav everywhere —
no per-template changes needed. Community (educator-authored) lessons
aren't in this sequence; they're freestanding for v1.

## Three ways to run a real circuit through Qiskit

`POST /api/compare-shots` (single-qubit: `H`/`X`/`Y`/`Z`/`RY:<deg>`)
and `POST /api/compare-shots-2q` (two-qubit: `X1`/`X2`/`H1`/`CNOT`)
both run a fixed gate list through real `qiskit-aer` server-side and
return counts. Single Qubit's Step 5, Python IDE's fixed snippets, and
the Circuit Builder all call whichever endpoint matches the qubit
count selected.

`POST /api/run-code` is the third, for Python IDE's actual code
editor — it accepts real-looking Python source, not a gate list. Since
running arbitrary user-submitted code server-side is a genuine
security problem, it's never passed to `exec()` directly: `app.py`'s
`_validate_circuit_code()` parses it with Python's own `ast` module
and walks the tree, allowing only `QuantumCircuit` construction, a
fixed gate/measure method allowlist, simple variable assignment, and
basic arithmetic — no imports, loops, function/class definitions, or
any name/attribute starting with `__` (closes classic sandbox-escape
patterns like `().__class__.__bases__` that don't even need a
dangerous call to work). No loops in the grammar also means there's
structurally no way to write an infinite loop; a `SIGALRM`-based
3-second timeout is defense in depth on top of that (a no-op on
Windows, where `SIGALRM` doesn't exist — only matters running the dev
server there; gunicorn/Docker deploys are Linux). Max 3 qubits, 60
operations, 4000 characters. See the comment block above
`/api/run-code` in `app.py` for the full reasoning, and
`futureplans.md` #12 for what a looser version might look like later.

All three endpoints degrade gracefully (`501` + a clear message) if
`qiskit`/`qiskit-aer` aren't installed, and none need sign-in — none
of this is account data.

## Sandbox deep links

`/sandbox` supports both `?topic=single|two|physical` and a hash
(`/sandbox#bloch`, `#two`, `#physical`) for linking straight to one
widget; clicking a tab updates the hash, so whatever you're looking at
is always a shareable URL.

## Embeddable widgets

`/embed/coin-flip` and `/embed/two-qubit` are deliberately chrome-less
pages (no sidebar/topbar/footer, no `X-Frame-Options`/CSP restriction)
meant to be dropped into an `<iframe>` on another site or course page —
same live `quantum.js`/`twoqubit.js` engine as everywhere else, just no
navigation around it. `demo-coin-flip.html` and `two-qubit.html` link
to their respective embed page and (coin-flip) include a ready-to-copy
`<iframe>` snippet. Both routes are open to everyone, same as `/demos`.

## The quantum "simulation" is real math

`static/js/quantum.js` implements actual complex numbers and 2×2
unitary matrices (H, X, Y, Z, RY(θ)) applied to real amplitude pairs
`[α, β]`. `static/js/twoqubit.js` does the same for a 4-amplitude
two-qubit state with X1, X2, H1, and CNOT. Measurement sampling uses
`Math.random()` weighted by `|amplitude|²` — Born's rule, not a lookup
table. `/api/compare-shots` in `app.py` runs the *exact same circuit*
through real `qiskit-aer` server-side, so Single Qubit's Step 5 and the
Python IDE can show genuine agreement (and genuine shot noise) between
this from-scratch engine and IBM's own simulator.

## The `challenge/` folder

A **standalone, self-contained** copy of the Single Qubit sandbox where
the actual physics (`quantum-challenge.js`) is left as TODOs — built so
you can implement the gate matrices and measurement logic yourself
without looking at the finished `static/js/quantum.js`. Doesn't run
through Flask; open `challenge/index.html` directly in a browser.
Instructions in `challenge/CHALLENGE.md`. Excluded from the Docker
image (`.dockerignore`) since it's a practice exercise, not part of the
deployed app.

## Deploying beyond Docker

Since this is a real (if small) Flask app, it deploys anywhere Python
apps do:

- **Render / Railway / Fly.io** — point them at the repo; most detect
  Flask automatically, or use the included `Dockerfile` directly.
- **A VPS** — `pip install -r requirements.txt`, then
  `gunicorn --bind 0.0.0.0:5000 app:app` behind nginx.
- Whatever you use, make sure `debug=False` (or run via gunicorn,
  which never uses Flask's debug server) before it's public.

## Known limitations, honestly

- **Usage stats (shots run/gates applied) are still local-per-browser**
  (`stats.js`, `localStorage`) — a deliberate scope cut, not migrated
  to the account backend along with lesson progress. Cosmetic counters,
  not account data.
- **`SECRET_KEY` defaults to an insecure dev value** if the env var
  isn't set — fine on localhost, must be set explicitly (see
  `.env.example`) before deploying anywhere real.
- **No notification when a creator request needs review** — an admin
  has to remember to check `/admin/creators`; nothing pings them.
- **No self-serve re-request after a creator rejection** — dead end
  for now, `/lesson-creator` just explains it.
- **Custom (community) lessons have no rich text, and their progress
  isn't surfaced outside the lesson page itself** — plain text bodies
  only (deliberate — see "Lesson Creator" above for why), no version
  history once edited, and Dashboard/Account don't know about
  `custom-<slug>` lesson ids yet even though the progress API does.
- **No real photographs.** Everything visual here is a hand-built SVG
  illustration/diagram — no network access in the environment this was
  built in to fetch real photos, and fabricating placeholder "photos"
  would misrepresent what they are.
- **Reality Check's hardware numbers** are publicly reported figures
  current as of when this was built and will go stale — worth a quick
  check before any live demo more than a few weeks out.
- **Python IDE's code editor has no loops** — the AST-restricted
  grammar behind `/api/run-code` allows straight-line code only (see
  "Three ways to run a real circuit through Qiskit" above for why that
  was the simplest safe choice for v1). Circuits have to be written out
  gate-by-gate.

See `futureplans.md` for the complete, detailed list of what's shipped
vs. deferred, with enough context to pick any of it back up later.
