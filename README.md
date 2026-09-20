# Qubit Sandbox

A Flask web app for learning quantum computing — lessons with live,
real-math sandboxes instead of static write-ups.

Live pages: a landing page, a personalized **Dashboard**, a full
**Lessons** catalog organized into **Modules** (Module 1 — QM Basics →
Single Qubit → Two Qubits → Physical Qubit → Hardware Lab → Reality
Check, plus its two widgets — followed by any published creator
modules and standalone community lessons, with prev/next navigation
through Module 1's sequence), a **Demos** hub (Coin Flip + Single
Qubit, no sign-in needed), a full-screen **Sandbox**, a **Python IDE**
with a real code editor (loops, branching, `print`, `input` — see
"Python IDE" below) plus runnable Qiskit snippets and a full-page
editor with an output console, a **Lesson Creator** + **My
Submissions** workspace for verified creator accounts (write lessons
with Markdown, custom checklists, and creator-built widgets; group
lessons into Modules; edit/delete/publish), gamification (daily
streaks, study-hours tracking, unlockable badges), an **Admin** page
for reviewing creator requests, and an **Account** page (profile,
stats, per-module/per-lesson progress, badges, account deletion).
**Sign-in is real** — Google OAuth + server sessions, backed by
Postgres (Supabase), with separate **Sign in** (`/login`) and **Create account**
(`/signup`, picks student/educator/creator) flows — see "Accounts"
below.

---

## Quick start

```bash
pip install -r requirements.txt
python app.py
```

Requires a Postgres database — see "Accounts" below for the
`DATABASE_URL` you need from Supabase before `app.py` will even boot
(it calls `db.register_app(app)` at import time, which needs to
connect). A free Supabase project takes about two minutes to create if
you don't have one yet: supabase.com -> New project -> once it's
provisioned, Project Settings -> Database -> Connection string -> URI.

Open **http://localhost:5000**. `debug=True` is on in `app.py`, so
editing a template or static file and refreshing picks up the change
immediately — no restart needed.

`qiskit` + `qiskit-aer` are in `requirements.txt` and power
`/api/compare-shots` (used by Single Qubit's Step 5 and the Python
IDE). They're imported lazily in `app.py`, so the rest of the app still
runs even if they're not installed — that one endpoint just returns a
501 with a clear message instead.

Sign-in requires real Google OAuth credentials — see "Accounts"
below to wire that up before `/login`/`/signup` will work.

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
├── db.py                      ← Postgres (Supabase): users, lesson progress, custom_lessons, modules, custom_widgets, shared_circuits, activity_log, badges
├── requirements.txt
├── Dockerfile
├── .dockerignore
├── .gitignore
├── .env.example                ← SECRET_KEY / DATABASE_URL / GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / CREATOR_EMAILS / ADMIN_EMAILS
├── futureplans.md             ← what's shipped, what's deferred, in detail
├── templates/
│   ├── base.html              ← sidebar app-shell, extended by every page below
│   ├── landing.html           ← standalone marketing/intro page, NO sidebar
│   ├── login.html             ← standalone sign-in page (returning users), NO sidebar
│   ├── signup.html            ← standalone create-account page (student/educator/creator picker), NO sidebar
│   ├── _lesson_nav.html       ← Jinja macro: prev/next lesson nav, included by every lesson template
│   ├── dashboard.html         ← personalized: onboarding panel, stats, module progress, gamification summary
│   ├── lessons.html           ← Module 1 + community modules + standalone lessons, all with progress bars
│   ├── account.html           ← @login_required: profile, stats, module/lesson progress, streaks, badges, danger zone
│   ├── admin-creators.html    ← @login_required + ADMIN_EMAILS: approve/reject pending creator requests
│   ├── demos.html             ← open-access hub: Coin Flip + Single Qubit
│   ├── demo-coin-flip.html    ← a working scaffold (live widgets, sparse narrative on purpose)
│   ├── sandbox.html           ← full-screen widgets, no lesson scaffolding, hash deep-links
│   ├── qm-basics.html         ← Lesson 0, open access
│   ├── single-qubit.html      ← Lesson 1, open access, full step-by-step format
│   ├── two-qubit.html         ← Lesson 2, gated
│   ├── physical-qubit.html    ← Lesson 3, gated
│   ├── hardware-lab.html      ← Lesson 4, gated — MOSFET diagram, LC-loop demo, chip-layout diagram
│   ├── reality-check.html     ← Lesson 5, gated
│   ├── lesson-creator.html    ← write/edit one lesson: Markdown, checklists, module + widget pickers
│   ├── creator-submissions.html ← "My Submissions": manage all your modules, lessons, and widgets
│   ├── custom-lesson.html     ← renders a published community lesson at /lessons/custom/<slug>
│   ├── python-ide.html        ← quick-run snippet editor + runnable presets + Circuit Builder
│   ├── python-ide-editor.html ← full-page IDE: code area, output console, gate reference, save-as-widget
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
        ├── gamification.js    ← site-wide activity heartbeat + badge-unlock toasts
        ├── stats.js           ← localStorage usage counters (shots run, gates applied)
        └── sw.js              ← PWA service worker (network-first for pages, cache-first for assets)
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
`Flask-Login`), backed by Postgres via Supabase (`db.py`: `users`,
`lesson_progress`, `custom_lessons`, and friends — see `db.py`'s
module docstring for the required `DATABASE_URL`).

**Sign in vs. create account.** `/login` is for returning visitors —
straight through to wherever they were headed. `/signup` is for new
visitors: pick an account type first (Student, Educator, or Creator —
see below), then Google sign-in, which applies the chosen type only if
the resulting account is freshly created (an existing account that
lands on `/signup` by mistake just signs in normally, keeping its
original type).

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

**Without those credentials set**, `/login` and `/signup` show
Google sign-in as unavailable (with an explanation) rather than
degrading to any other sign-in method — there isn't one.

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
progress, and any lessons/modules/widgets they've published (public
shared circuits and confusion reports are anonymized rather than
deleted, so a link someone else has doesn't break). `db.delete_user()`
handles the cascade manually — foreign keys are always enforced in
Postgres (no equivalent of SQLite's opt-in `PRAGMA foreign_keys`), so
dependent rows have to go first, in dependency order.

## Modules

`/lessons` groups the whole catalog into **Modules** instead of one
flat list. **Module 1** is built-in (`db.get_builtin_module()`,
seeded on first run) and holds the 6 original lessons plus the two
embeddable widgets. Verified creators can create their own module
(`POST /api/creator-modules`), assign any of their lessons to it (a
per-lesson module picker in the Lesson Creator, or a quick-reassign
dropdown on My Submissions), and publish it — which also bulk-publishes
every lesson currently in it (`POST /api/creator-modules/<id>/publish`).
`/api/modules` returns the whole catalog (built-in + published
community modules, each with its lessons) and is what `/lessons`,
`/dashboard`, and `/account` render their module-grouped progress bars
from, paired with the existing `/api/progress` data.

## Lesson Creator, My Submissions & creator widgets

`/lesson-creator` shows one of several things depending on who's
looking: signed-out gets the pitch + a `/signup` link; signed-in
non-creators get a "request creator access" button; pending/rejected
creators get a status message; **verified creators** get a real
authoring form (`?edit=<id>` loads an existing lesson of theirs into
it instead of starting fresh):

- **Create/edit**: title, short description, an optional Module, and
  up to 12 steps. Each step has a title, a **Markdown** body (rendered
  server-side with `Markdown` + sanitized with `bleach` before
  storage — see "Markdown" below), an optional widget (the built-in
  Coin Flip/Two Qubit embeds, or one of the creator's own saved
  widgets), and up to 6 custom checklist items (extra
  progress-tracked checkboxes beyond "mark step complete").
  `POST`/`PUT /api/lessons(/<id>)` validate everything server-side and
  write to `custom_lessons` via `db.create_custom_lesson()` /
  `db.update_custom_lesson()`; slugs auto-generate from the title
  (collisions get `-2`, `-3`, ... appended).
- **My Submissions** (`/creator/submissions`) is the management page:
  every module, lesson, and widget you've authored, with
  edit/delete/publish controls and a quick lesson→module reassign
  dropdown — separate from the Lesson Creator so that page can stay
  focused on writing one lesson at a time.
- **Creator widgets**: a verified creator can save a restricted Qiskit
  snippet as a reusable widget — either from the Lesson Creator's step
  editor ("+ Create new widget") or from the Python IDE's full-page
  editor ("Save as widget", see below) — then pick it from any step's
  widget dropdown. Stored in `custom_widgets`, validated with the
  exact same `_validate_circuit_code()` AST-walker `/api/run-code`
  uses, and rendered read-only with a "Run" button that calls
  `/api/run-code` — no new execution surface.
- **Publish, unpublish, delete** your own lessons/modules/widgets, all
  checked server-side against ownership (a non-owner's attempt gets a
  real `403`). An unpublished lesson stays visible to its own author
  (to preview before republishing) but 404s for everyone else — same
  response as a nonexistent slug, so it doesn't leak that an
  unpublished lesson exists.

Published lessons render at `/lessons/custom/<slug>`
(`custom-lesson.html`) and appear grouped by module (or under "Other
community lessons" if standalone) on `/lessons` — open to everyone, no
sign-in needed to *read* one, though marking steps/checklist items
complete needs an account, same as any other lesson
(`initLessonProgress('custom-<slug>')`, tracked under a
`custom-`-prefixed lesson id so it can't collide with the 6 built-in
ones). That progress now IS surfaced on Dashboard/Account via the
Modules catalog above.

## Markdown

Lesson step bodies support most of the common Markdown feature set —
headings (h1–h6), **bold**/*italic*/***both***, `` ~~strikethrough~~ ``,
`==highlighted==` text, inline code and fenced code blocks (syntax-
highlighted client-side with highlight.js, loaded from a CDN in
`custom-lesson.html`), nested bullet/numbered lists, links, images,
horizontal rules, task-list checkboxes, tables, blockquotes, and
Obsidian-style callouts (`> [!NOTE]`, with an optional custom title and
a `-`/`+` suffix for a foldable `<details>` callout, e.g.
`> [!FAQ]- Are callouts foldable?`). Extensions used: `fenced_code`,
`tables`, `sane_lists`, `pymdownx.tilde`, `pymdownx.mark`,
`pymdownx.tasklist`, plus a small custom `ObsidianCalloutExtension` in
`app.py` (a `Treeprocessor` that turns marker-prefixed blockquotes into
styled callout blocks) since python-markdown/pymdown-extensions don't
ship GFM/Obsidian-style blockquote callouts out of the box. Everything
the library produces is still run through `bleach.clean()` against a
fixed tag/attribute allowlist before it's stored — Markdown's own HTML
output isn't trusted automatically. As with everything else here,
markdown is a *list*, not exhaustive Obsidian parity (e.g. inline
`[[wikilinks]]` and `#tags` aren't rendered specially).

## Gamification

Signed-in accounts get a lightweight activity heartbeat
(`static/js/gamification.js`) that pings `POST /api/activity/ping`
roughly once a minute while a tab is open and focused, logging one
"minute studied" for today (`activity_log`, one row per user per UTC
day) and re-checking every badge condition
(`compute_and_sync_badges()` in `app.py`). Badges
(`db.BADGE_CATALOG`) cover streaks (3/7/30 consecutive days), a
weekend-studier badge, 10/40 total study hours, lesson-completion
milestones (first lesson, 5 lessons, all of Module 1), and early-
bird/night-owl timing — newly-earned ones pop a toast
(`gamification.js`) and everything's summarized on Account (full badge
grid + streak/hours stats) and Dashboard (compact version). This is a
coarse "were you actively here" signal, not a precise or billing-grade
timer, and is stated as such in the UI copy itself.

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
and walks the tree. The allowed grammar is now broader than a
straight-line script — `for`/`while` loops, `if`/`elif`/`else`
branching, `print()`, and `input()` are all allowed alongside
`QuantumCircuit` construction, the gate/measure method allowlist,
variable assignment, and arithmetic — but imports, function/class
definitions, and any name/attribute starting with `__` are still
rejected (closes classic sandbox-escape patterns like
`().__class__.__bases__` that don't even need a dangerous call to
work). Because loops are now allowed, runaway execution is bounded
three ways instead of relying on "no loops in the grammar" alone: a
`SIGALRM`-based 3-second wall-clock timeout (a no-op on Windows, where
`SIGALRM` doesn't exist — only matters running the dev server there),
a hard cap on loop iterations enforced at `for`/`while` AST nodes
before execution, and a *runtime* operation counter (gate/measure
calls actually made while the code runs, not just how many appear in
the source) that aborts once it crosses the same 60-operation ceiling
straight-line code was already held to. `print()` output is captured
and returned as `stdout` alongside the measurement counts, shown in
the Python IDE's console panel. `input()` reads from an optional
client-supplied `stdin` string (one value per line, popped in order) —
there's no real interactive terminal server-side, so a program that
calls `input()` past the end of the supplied lines gets an empty
string rather than hanging. Max 3 qubits, 60 operations, 4000
characters, 200 total loop iterations. See the comment block above
`/api/run-code` in `app.py` for the full reasoning.

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
- **Custom (community) lessons have no version history** once edited —
  an edit overwrites the previous content of that lesson.
- **No real photographs.** Everything visual here is a hand-built SVG
  illustration/diagram — no network access in the environment this was
  built in to fetch real photos, and fabricating placeholder "photos"
  would misrepresent what they are.
- **Reality Check's hardware numbers** are publicly reported figures
  current as of when this was built and will go stale — worth a quick
  check before any live demo more than a few weeks out.
- **Study-time/streak tracking is a coarse heartbeat**, not a precise
  timer — see "Gamification" above.

See `futureplans.md` for the complete, detailed list of what's shipped
vs. deferred, with enough context to pick any of it back up later.
