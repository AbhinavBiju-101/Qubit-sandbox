# Future Plans

A running log of what's shipped and what's intentionally left for later.
This file has been through a few rounds of parallel work and merging
(see git history / commit messages if that context is useful) — it
reflects the single combined, current state after each merge.

---

## Recently shipped (this round — the widget sweep: open demo + embed pages)

- **Investigated before building, per the "check first" note from last
  round: `/demos` *is* the real widgets gallery**, not the catalog's
  unused `widgets` field (confirmed via grep — that field is written
  to the catalog dict but never rendered by any template; it's inert).
  `/demos` is open, no sign-in, hand-curated, and had a literal "More
  on the way" placeholder card. The actual gap: every Module 2-6
  lesson is `@login_required`, so none of their 25 real widgets had
  any open-access equivalent the way Coin Flip (Module 1) does.
- **Added 3 curated open demo + embed page pairs**, following the
  exact existing `/demos/coin-flip` + `/embed/coin-flip` pattern
  precisely (same minimal chrome-less embed shell, same "get embed
  code" `<details>` block, same in-shell demo page structure):
  Grover's Search (Module 2 — an algorithm), the double-slit (Module
  4 — a physics visual), and BB84 (Module 6 — a crypto demo). One
  from each broad category, not all 25 — opening everything would
  just duplicate `/lessons` and defeat the point of the sign-in gate
  on the full lessons.
  New routes: `/demos/grovers-search`, `/demos/double-slit`,
  `/demos/bb84` (full pages, in the normal sidebar shell) and
  `/embed/grovers-search`, `/embed/double-slit`, `/embed/bb84`
  (chrome-less, iframe-ready, no restrictive frame headers — same
  reasoning as the existing two embeds). `demos.html`'s placeholder
  card replaced with the three real ones; `BUILTIN_WIDGETS` extended
  to match, for whenever that field does get a consumer.
  Every widget's JS is a direct copy of its already-verified full-
  lesson logic (not reimplemented) — confirmed via a structural diff
  against the original files that the copied `mq.*` call sequences
  (Grover) and `prepare`/`measure` function bodies (BB84) are
  byte-identical, not just "looks the same," before shipping.

---

## Recently shipped (previous round — 4th-step sweep completed across Modules 3-6; theory gap fixed)

- **Bug fix, called out directly: Operator Types' Step 1 theory was too
  compressed** (three terse stat-card labels, no real prose explaining
  *why* Hermitian/Unitary/Projection matter). Rewrote it with a full
  paragraph per property — what it means physically, and the specific
  theorem each one is standing in for (real eigenvalues, preserved
  probability, idempotent collapse) — with the stat cards kept as a
  quick-reference summary underneath instead of the only explanation.
  Worth checking the other 20 lessons below for the same failure mode
  if anything still reads thin.
- **All 21 remaining Module 3-6 lessons now have the 4th "explain
  more, cover more" step**, completing the sweep Module 2 started two
  rounds ago. Every module's own step 4 is listed in the lesson files
  themselves; the short version: Module 3 connects the math to what's
  already been simulated (outer products → projectors, CNOT as a 4×4
  matrix, the 2ⁿ-dimension wall, degenerate eigenvalues, the
  Robertson uncertainty bound); Module 4 connects the physics to real
  systems (electron microscopes, quantum dots, alpha decay, scanning
  tunneling microscopy, real atomic orbital degeneracy) plus one
  genuinely mind-bending verified-real experiment (delayed choice,
  framed carefully — no backward-in-time causation implied); Module 5
  goes from toy code to what's actually deployed (T2≤2T1, surface
  codes, quantum volume); Module 6 covers the field's real present-
  tense response (E91/device-independent QKD, NIST's already-
  standardized post-quantum cryptography).
  New computed content, not just prose, where it was cheap and added
  real value: a live 2ⁿ-amplitude calculator (Tensor Products) and a
  real Stefan-Boltzmann P=σT⁴ calculator (Blackbody Radiation) —
  the latter's solar-temperature output checked against the known
  real value (~64 MW/m² at 5800K) before shipping. Step counts (3→4)
  updated for all 21 lessons in both `app.py` and `lessons-data.js`;
  verified via grep that every touched template has exactly 4
  `data-step` blocks, not silently 3 or 5.
- **All factual claims added this round were ones I was confident
  in from training** (Stefan-Boltzmann's exact constant, T2≤2T1,
  NIST's 2024 PQC standardization, E91's 1991 date, Gamow's 1928
  alpha-decay theory) — nothing here needed a web search, and nothing
  time-sensitive was asserted as still-current without flagging it
  as such (quantum volume's role, current fidelity numbers).

---

## Recently shipped (previous round — Bloch sphere upgrade, custom qubit setter, account scroll fix, card icons)

- **Bug fix: `/account`'s "Lesson progress" section grew the whole page.**
  Now `max-height:420px; overflow-y:auto` on that one panel — scrolls
  internally instead of pushing everything below it down the page.
- **`bloch.js` upgraded — every lesson using `createBlochWidget()`
  benefits automatically, no template changes needed anywhere.**
  Added: ket labels at all six cardinal points (|0⟩,|1⟩,|+⟩,|−⟩,|+i⟩,|−i⟩),
  reference X/Y/Z axis lines, projection ("shadow") guide lines from
  the vector tip down to the equatorial plane and back to the origin
  (the standard textbook way of reading theta/phi off a drawn vector),
  and a front/back depth cue: this projection only pushes the Y-axis
  diagonally (X and Z stay true-length, in-plane), so Y<0 is exactly
  "behind the sphere" — drawn dashed and faded, on both the live state
  vector and the reference Y-axis's own negative half, consistently.
  `set(theta, phi, mag)`'s signature is unchanged, so this is a pure
  drop-in — verified the six pole projections land exactly where
  expected (Node, pure-math check on the extracted projection
  functions) before shipping.
- **New "Custom State" tab on `/sandbox`.** Single-qubit: theta/phi
  sliders driving a live Bloch sphere, *or* raw α/β amplitude inputs
  (auto-normalized on "Normalize & apply", global phase correctly
  stripped via the same convention `Qubit.bloch()` already uses) —
  both paths show the live wavefunction and the nearest named ket
  (|0⟩/|1⟩/|+⟩/|−⟩/|+i⟩/|−i⟩, or "general superposition" if it's none
  of those). Two-qubit: independent A1,B1 / A2,B2 amplitude entry per
  qubit, each auto-normalized, with two separate Bloch spheres and the
  computed tensor-product joint wavefunction — explicitly cross-linked
  to Tensor Products (Module 3), including the "there's no way to reach
  an entangled state this way" point. The angle↔amplitude round-trip
  math (including unnormalized, arbitrary-global-phase input) and the
  named-ket detector were verified in Node against known values before
  shipping, not just eyeballed.
- **Lesson cards on `/lessons` for Modules 2-6 got per-lesson icons and
  rotating colors**, matching Module 1's per-lesson variety instead of
  one repeated pencil icon and one flat module-wide color. 25 new
  hand-authored SVG icons (one per lesson, thematically matched —
  a magnifying glass for Grover's Search, a key for BB84, a cube for
  the 3D box, etc.), added as a `LESSON_ICONS` dict in `lessons.html`
  fed by a new `icon` key on every lesson dict in `app.py`. All 25
  validated as well-formed SVG/XML before shipping (a malformed path
  injected via `|safe` fails silently in a browser, so this was worth
  checking programmatically rather than trusting hand-typed path data).

---

## Nothing currently deferred

Both items from the earlier "explicitly deferred" list (the 4th-step
sweep, and the widgets gallery) are done as of this round and the
previous one. Nothing is known to be intentionally left undone right
now — if something surfaces, it goes here rather than being dropped
silently, per how this file has worked throughout.

---

## Recently shipped (previous round — card bugs fixed; Module 2 deepened)

- **Bug fix: per-lesson descriptions were missing on Module 2-6 cards.**
  `_module_catalog()`'s list comprehensions only carried id/title/href/
  steps — no `description` — so `/lessons`' community-module-loop cards
  (which every Module 2-6 lesson renders through) had nothing to put in
  the `<p>` tag Module 1's hand-written cards always had. Added a
  `description` field to every lesson dict in `LESSON_ORDER` and every
  `MODULE_N_LESSONS` list (Module 1's text copied verbatim from its
  existing hardcoded cards, for consistency), propagated through all 6
  catalog list comprehensions, and added `<p>{{ l.description }}</p>`
  to the community-loop card template.
- **Bug fix: per-lesson progress bars were missing on Module 2-6 cards
  (reported as a mobile issue, but it was missing everywhere — mobile
  is just where it's more obviously wrong with no desktop sidebar for
  contrast).** The community-loop cards only ever had a *module-level*
  aggregate bar; Module 1's cards each have their own bar wired to a
  fixed DOM id. Rather than hardcode 25 more ids, gave each card a
  generic `.lesson-progress-row[data-lesson-id][data-lesson-steps]`
  and extended the existing `QS_LESSON_DEFS.forEach` progress loop
  (which already fetches real per-lesson step-completion data) to
  populate any element matching that selector — exact step-level
  percentages, same `qsComputePct` Module 1 uses, not the coarser
  "touched at all" approximation the module-level bars still use.
  Also gave Module 2-6 cards `data-lockable="true"` + `.lock-pill`/
  `.lock-progress` classes so the signed-out state (hide progress,
  show "sign in to unlock") now works on them exactly like Two Qubits
  onward already did for Module 1.
- **Module 2 deepened — 4th step added to all 4 lessons**, as a first
  installment of "add more steps, explain more, cover more" (too large
  to do for all ~37 lessons in one pass — see note below). Teleportation
  gained a real-world-grounding step (quantum repeaters, the 2017
  Micius satellite demonstration, chip-to-chip teleportation); Superdense
  Coding gained an honest "this isn't free bandwidth" cost discussion
  (the Bell-pair setup is a real, just pre-paid, cost); Deutsch-Jozsa
  gained a "why does anyone care about a fake problem" framing (1992,
  first *provable* quantum speedup, historically decisive despite zero
  direct practical use); Grover's Search gained a real classical-vs-
  quantum query-count calculator at N up to 1,048,576, plus the
  "quadratically optimal, provably" note. All step counts (3→4) updated
  in `app.py`, `lessons-data.js`, and each template.
- **Not done yet, flagged rather than silently skipped:** the same
  "one more step, real-world grounding" treatment for Modules 3, 4, 5,
  and 6 (27 more lessons) — Module 2 was chosen first as the newest,
  most-recently-built module. Whether to sweep the same treatment
  through the rest, and in what order, is an open question for the
  next round rather than something assumed here.
- **VIT syllabus re-check (asked again this round):** re-scanned the
  original four-module syllabus topic-by-topic against what's now
  built. No further gaps found beyond the 6 filled in last round —
  if a specific term is still missing, it should be named explicitly
  rather than assumed, since guessing further without a concrete gap
  risks inventing lessons that don't map to anything real.

---

## Recently shipped (previous round — filling VIT syllabus gaps in Modules 3 & 4)

- **Module 3 gained 5 lessons** (`basis-vectors`, `tensor-products`,
  `operator-types`, `eigenvalues-eigenvectors`, `commutation-relations`),
  covering VIT Module 2 topics that were only touched in passing before:
  linear vector space/orthonormal bases/Hilbert space, tensor products
  of vector spaces, Hermitian/Unitary/Projection operators, eigenvalues
  and eigenvectors, and a dedicated commutation-relations lesson (the
  H/Z non-commuting demo from Matrices as Gates was a preview, not the
  full treatment). Tensor Products' "try to factor a Bell state back
  apart" search is a real 5,000-random-sample numerical search each
  run — verified against a 2,000,000-sample reference run that the
  true floor is 2-√2 ≈ 0.586, so the lesson's "never gets close" claim
  is a real mathematical fact, not a hand-wave.
- **Module 4 gained 1 lesson** (`three-dimensional-box`), extending
  Particle in a Box's 1D treatment (and its degeneracy bonus paragraph)
  into VIT's explicitly-named "extension to three-dimensional potential
  wells" — a genuine computed degeneracy search over nx,ny,nz up to 6,
  not a lookup table.
- **Remaining VIT coverage check, for whoever reads this next:** with
  this round, Module 3+4 now cover essentially all of VIT's Modules
  1–4 (wave-particle duality, math foundations, postulates,
  applications) at an applied/simulated depth rather than full
  derivation depth. Module 1 (built before this project's Module 2-6
  work) already covers VIT's Module 5 (qubits, Bloch sphere,
  entanglement, Bell states, Pauli/Hadamard/CNOT). No further known
  gaps against the syllabus as of this round — if new ones surface,
  log them here rather than guessing silently.
- **Verification.** Same discipline as the Module 2/5/6 round: every
  new interactive claim was checked by actually running the logic in
  Node against known theory, not just eyeballed — operator
  classification checked against all 6 candidate matrices' known
  Hermitian/Unitary/Projection status, the eigenvector checker against
  all 8 (operator, vector) combinations' known eigenvalue theory, and
  the tensor-product factorization floor against a 2M-sample reference
  run. All passed. Still no live server smoke test possible in this
  sandbox (no network for `pip install authlib`).

---

## Recently shipped (previous round — Modules 2, 5 & 6; Modules 1–6 complete)

- **Module 2 — "Quantum Algorithms" — done.** Four lessons
  (`quantum-teleportation`, `superdense-coding`, `deutsch-jozsa`,
  `grovers-search`), built after Modules 3/4 at the person's request
  but slotted back into catalog position 2 (`ALL_BUILTIN_LESSONS` order
  is 1→2→3→4→5→6). Introduced `static/js/multiqubit.js` — a real
  N-qubit state-vector engine (arbitrary n, full CNOT/measurement/
  Grover-diffusion support) built on the same `C` complex-number
  helper as `quantum.js`, needed once a lesson goes past 2 qubits.
  Teleportation and Superdense Coding read amplitudes directly off the
  post-measurement register rather than faking the "it matched"
  reveal. Grover's Search deliberately uses N=4 (2 qubits), not the
  originally-planned 3 qubits — 1 iteration gives an exact 25%→100%
  jump at N=4, which is a cleaner demo than any 3-qubit case.
- **Module 5 — "Error Correction & Noise" — done.** Three lessons
  (`decoherence`, `bit-flip-code`, `nisq`). Decoherence reuses
  `bloch.js`'s existing `set(theta, phi, mag)` third argument (already
  in the engine, just previously unused by any lesson) to show the
  vector's length shrinking. The bit-flip code lesson runs a genuine
  5-qubit (3 data + 2 syndrome ancilla) non-demolition error-correction
  circuit on `multiqubit.js` — ancillas get measured, data qubits'
  superposition never does. NISQ's circuit-depth calculator plots the
  real `(1-ε)^N` curve.
- **Module 6 — "Quantum Cryptography" — done.** Two lessons (`bb84`,
  `shors-algorithm`). BB84 runs 16 independent single-qubit trials
  through `quantum.js` with an Eve intercept-resend toggle — the
  ~25%-error-rate-with-Eve result falls out of the real simulation,
  it isn't hardcoded. Shor's lesson is explicitly scoped to the
  classical period→factors half (N=15, real gcd/modpow arithmetic);
  the quantum period-finding half is described but not simulated, with
  an explicit "NISQ hardware isn't there yet" caveat.
- **Modules 1 through 6 are now all complete.** Module 7 ("From Lab to
  Industry") remains unbuilt and unscheduled.
- **Plumbing.** `_module_catalog()`, `ALL_BUILTIN_LESSONS`/`_lesson_nav()`,
  `lessons.html`'s community-module-loop reuse, and `lessons-data.js`
  (`QS_LESSON_DEFS`) all extended the same way Modules 3/4 were —
  see that entry below for the mechanism. No template or JS
  architecture changed for this round beyond adding `multiqubit.js`.
  Same caveat as last round applies: no live server smoke test was
  possible in the build sandbox (no network to `pip install authlib`);
  only static checks (Python AST/compile, all-template Jinja
  compilation, route/function-name uniqueness, CSS class coverage)
  were run. Worth a real click-through — especially the multi-qubit
  circuits in Module 2/5, which are the most novel code in the app —
  before deploying.

---

## Recently shipped (previous round — Modules 3 & 4)

- **Module 3 — "The Physics and Math Underneath" — done.** Five lessons
  (`complex-numbers`, `bra-ket`, `matrices-as-gates`,
  `measurement-postulate`, `schrodinger-equation`), placed *after* the
  original Module 1 rather than before it on purpose — every lesson
  leans on gate/Bloch/entanglement intuition the person already built,
  instead of front-loading linear algebra. All five reuse the real
  `quantum.js` engine (no toy math): Complex Numbers applies an actual
  phase gate; Bra-Ket computes real inner products; Matrices as Gates
  expands the arithmetic by hand with the live α/β; Measurement builds
  a Stern-Gerlach simulator plus the sequential Z→X→Z cascade; Schrödinger
  animates real precession and Rabi flopping via `requestAnimationFrame`.
- **Module 4 — "Where Quantum Comes From" — done.** Five lessons
  (`wave-particle-duality`, `blackbody-radiation`, `de-broglie`,
  `particle-in-a-box`, `quantum-tunneling`), covering the historical/
  physical origin story a computing-first Module 1 skips. Each has a
  genuine computed simulation on `<canvas>`/SVG (double-slit build-up
  with a which-path-detector toggle, real Planck's-law vs.
  Rayleigh-Jeans curves, a log-scale de Broglie ruler, particle-in-a-box
  wavefunctions, an exponential tunneling-barrier sim) — Quantum
  Tunneling explicitly cross-links back to Hardware Lab's Josephson
  junction, since it's the same mechanism at chip scale.
- **Plumbing for a 2nd/3rd built-in module — done.** `_module_catalog()`
  in app.py generalized from "just Module 1" to a list of builtin
  modules; `_lesson_nav()` now walks one continuous `ALL_BUILTIN_LESSONS`
  sequence for prev/next; `lessons.html`'s existing community-module
  loop renders extra builtin modules too (via a `kind == 'builtin'`
  branch so they don't get a "BY community" byline); `lessons-data.js`
  (`QS_LESSON_DEFS`) got the new entries so Dashboard's "Continue"
  list and lesson-count stat pick them up for free. Module 1's own
  progress bar on `/lessons` was carefully kept scoped to its original
  six lessons (not accidentally averaged across every builtin lesson)
  — see the `idToFill.hasOwnProperty(l.id)` guard in `lessons.html`.

---

## Recently shipped (this round — Supabase/Postgres migration)

- **Migrated off SQLite to Postgres (Supabase) — done.** SQLite's
  whole-database write lock was becoming a real bottleneck as the
  Modules/gamification/sharing features above grew the write volume,
  and a single on-disk file doesn't survive a redeploy on most hosts
  without a mounted volume anyway. `db.py` now connects to Postgres via
  `psycopg2` (see its module docstring for the required `DATABASE_URL`
  and exactly which Supabase connection string to use). A `_PGConn`
  wrapper mimics SQLite's connection-level `.execute()` so the large
  majority of functions needed zero logic changes — what genuinely
  needed per-function attention: `cur.lastrowid` (SQLite-only) ->
  `INSERT ... RETURNING id`, `INSERT OR IGNORE` -> `ON CONFLICT DO
  NOTHING`, `PRAGMA table_info` -> `information_schema.columns`, and
  reordering `modules` before `custom_lessons` in the schema (Postgres
  validates foreign-key targets at `CREATE TABLE` time; SQLite only
  checks at write time, so the old ordering silently worked there and
  silently failed on Postgres).
  Tested against a real local Postgres instance (not just written and
  assumed correct) — every function in `db.py`, plus a full app-level
  regression pass through Flask. Two real bugs turned up along the way
  that were independent of the migration itself: an aggregate query
  relied on `sqlite3.Row`'s integer indexing, which `psycopg2`'s
  dict-style rows don't support; and `delete_user` never cleaned up
  modules/widgets/shared circuits/confusion reports a user had
  created — a latent bug from before this migration, just never
  exercised by a test that deleted a user who owned more than a lesson
  or two. Both fixed, with public/shared content anonymized rather
  than deleted so someone else's link to it doesn't break.
- **`requirements.txt`**: `psycopg2-binary` added.
- Docs (`README.md`, `.env.example`, `app.py`/`db.py` docstrings,
  `account.html`) updated to describe Postgres instead of SQLite —
  several were still describing the old SQLite-backed setup.

## Recently shipped (previous round — intent-based feature branches)

- **Modules — done.** A `modules` table groups lessons into named,
  ordered sets instead of one flat list. A seeded "Module 1" holds the
  original six built-in lessons + the two embeddable widgets;
  verified creators can create their own module, assign their lessons
  to it, and publish it (bulk-publishing its lessons at once). Module-
  level progress bars on `/lessons`, Dashboard, and Account.
- **Gamification — done.** `activity_log` (a 60s site-wide heartbeat
  while a tab is open+focused) and `badges` tables. Streaks (current +
  longest, computed from consecutive UTC days), total hours studied,
  and 11 badges (3/7/30-day streak, weekend studier, 10/40-hour club,
  first lesson, five lessons, Module 1 complete, early bird, night
  owl), with an unlock toast and a badge grid on Account/Dashboard.
- **Lesson Creator v2 — done.** Markdown step bodies (see below),
  custom checklist items per step (extra progress-tracked checkboxes
  beyond "mark step complete"), creator-saved widgets (a restricted
  Qiskit snippet, built from the Python IDE's "Save as widget", or
  directly in the Lesson Creator), and a dedicated **My Submissions**
  page (`/creator/submissions`) for editing/deleting/publishing
  lessons, modules, and widgets, separate from the "write a new
  lesson" form.
- **Markdown, for real — done.** Supersedes the old "plain text only"
  decision below. `Markdown` + `pymdown-extensions` render step bodies
  to HTML, sanitized through `bleach` before storage — headings h1–h6,
  fenced code (syntax-highlighted client-side via highlight.js),
  bold/italic/strikethrough/`==highlight==`, nested lists, task-list
  checkboxes, tables, links, images, and Obsidian-style foldable
  callouts (`> [!NOTE]`, `> [!TIP]-`, etc. — a custom Markdown
  Treeprocessor, see `_ObsidianCalloutTreeprocessor` in `app.py`).
  Three real parser quirks found and fixed along the way: ATX-header
  regex backtracking on `#tag`-without-space, `nl2br` eating callout
  bodies, and adjacent blockquotes merging into one.
- **Python IDE — loops, branching, print/input — done.** Supersedes
  "no loops at all" below. `for`/`while`, `if`/`elif`/`else`,
  `print()`, and `input()` (batch-style, from an optional stdin box)
  are now allowed. Since a static AST pass can no longer bound total
  gate count once loops exist, `_run_validated_circuit` wraps every
  allowed `QuantumCircuit` method with a live counter that aborts
  mid-loop past 60 operations, plus a `sys.settrace` step counter
  (200k steps) that kills a CPU-spinning loop almost instantly instead
  of waiting out the 3s `SIGALRM` timeout. Both editors (quick-run
  panel + the new full-page `/python-ide/editor`) got CodeMirror for
  real syntax coloring and a working Tab key, plus a console panel
  that appends every run instead of overwriting the last one.
- **Two real bugs fixed:** the service worker was cache-first even for
  HTML pages, so a just-completed sign-in/out wasn't reflected until a
  second navigation — now navigation requests are network-first, only
  static assets stay cached. `/admin/creators` had no link anywhere in
  the UI (worked fine, just undiscoverable) — added a conditional
  Admin sidebar item with a pending-count badge.
- **Production cleanup.** No demo/guest account exists in the working
  app (there's a stale reference to one below and it's now corrected —
  it must have been removed by this project's original author before
  this file was last touched); hackathon-era references removed from
  the landing page and this file.

## Intent-based feature roadmap (previous round's brainstorm)

Organized by *who's using the app and why*, not by subsystem — the
same feature looks different depending on which of these someone
showed up as. Each item is tagged with its status as of this file.

### "I'm curious, just let me poke at something" (anonymous visitor)

- **Shareable circuit links** (`/share/<hash>`) — build something in
  the Sandbox/Python IDE, get a permanent URL that reproduces it
  exactly. **[Shipped this round]** — see `shared_circuits` table,
  `/share/<hash>`, and the Share button in the Python IDE.
- **Embeddable widgets** — an `<iframe>` snippet for someone else's
  blog/course page. **[Shipped this round]** — `/embed/circuit/<hash>`
  reuses the share mechanism above; a "Copy embed code" button sits
  next to the share link.
- **"Surprise me" on the landing page** — a random pre-built circuit
  that runs itself on load, no signup, no lesson framing.
  **[Shipped this round]** — see the widget on `landing.html`.

### "I want to actually learn this" (student, working through a module)

- **A "confused here" button on any step** — logs which step, no
  routing anywhere, just data for creators/admins on where people get
  stuck. **[Shipped this round]** — `step_confusion_reports` table,
  wired generically into `lesson-progress.js` so it works on every
  lesson (built-in and custom) for free, no per-lesson-type work.
- **Spaced-repetition nudge** — "You did Single Qubit 9 days ago,
  still at 60% — want to pick it back up?" on the Dashboard, computed
  from existing progress + `activity_log`, no new tracking needed.
  **[Shipped this round]**.
- **Predict-then-verify step type** — some steps could ask "guess the
  distribution" before running the widget, instead of only
  read-then-check. **[Not started]** — needs a new step-schema field
  (`predict: true`) and Lesson Creator UI; a real design decision
  (where's the "reveal" line, does a wrong guess count against
  progress) more than a coding task. Left for a dedicated round.
- **Cross-lesson glossary** — hover a bolded term (amplitude,
  decoherence, entanglement) for a one-line popover instead of
  re-explaining it every lesson. **[Not started]** — needs a curated
  term list (accuracy matters more than coverage here) and a way to
  mark terms in both built-in (hardcoded HTML) and custom (Markdown)
  lessons without hand-editing every existing lesson body.

### "I want to prove I learned this" (motivated / gamified student)

- **Shareable completion cards** — an OG-image-style card for "Module
  1 complete," screenshot/share-able like a Duolingo streak card.
  **[Not started]** — needs server-side image generation (Pillow),
  doable but a heavier dependency than anything else on this list;
  next round.
- **Scoped, opt-in leaderboards** — per-module or "this week," not a
  single global ranking (which mostly demotivates everyone not near
  the top). **[Not started]** — needs a real product decision on
  default-on-vs-opt-in and what "scoped" means exactly before it's a
  coding task.
- **A certificate page** — not legally meaningful, a nice static
  summary of what someone's done, downloadable as PDF. **[Not
  started]** — the `pdf` skill covers PDF generation technically; the
  content/design of "what goes on it" needs deciding first.

### "I want to teach with this" (creator)

- **Fork a lesson** — start from someone else's published lesson
  instead of blank, with attribution to the original. **[Shipped this
  round]** — `POST /api/lessons/<id>/fork`, a "Fork this lesson"
  button on any published custom lesson.
- **Draft/preview mode** — publishing used to be immediate; now a
  lesson can be created as a draft with a shareable, unguessable
  preview link that works even while unpublished, instead of only
  being visible to its own author. **[Shipped this round]** — see
  `preview_token` on `custom_lessons`, `/lessons/custom/<slug>/preview/<token>`.
- **Lesson analytics for creators** — aggregate (not per-user) step
  completion counts on your own lessons only. **[Shipped this
  round]** — derived directly from existing `lesson_progress` rows
  (no new tracking table — every step checkbox already writes there),
  see `db.get_lesson_step_completion_counts`; a bar-per-step view on
  My Submissions.
- **Co-authoring** — invite another creator to a module. **[Not
  started]** — needs an invite/accept flow and a real permissions
  model (can a co-author delete the module? edit others' lessons
  inside it?) worth its own round rather than bolting on quickly.

### "I want to build something, not just read" (tinkerer, post-Module-1)

- **Playground gallery** — public, opt-in shared circuits, lower
  stakes than publishing a whole lesson. **[Shipped this round]** — an
  optional "list publicly" checkbox on the share flow above, browsable
  at `/gallery`.
- **OpenQASM import/export** — bring a circuit in from elsewhere, or
  take one out. **[Shipped this round]** — Export/Import buttons in
  the Python IDE using Qiskit's own `qasm2` support, still funneled
  through the same AST validator on import (a pasted-in QASM file
  isn't a trust boundary bypass).

---

## Older items (predate this round; kept for reference)

- **Real account types — student / educator / creator — done.** `/signup`
  (distinct from `/login`) lets a new visitor pick a type before
  authenticating; Google/Demo Guest buttons carry the choice through
  and it's applied only if the resulting account is freshly created
  (`db.get_or_create_user` now returns `(row, was_created)`). Student
  and educator are instant; **creator needs verification** —
  `CREATOR_EMAILS` env var auto-verifies a matching, Google-verified
  email instantly, everyone else goes to `creator_status='pending'`
  and needs an admin (`ADMIN_EMAILS` allowlist) to approve them at the
  new `/admin/creators` page. An existing student/educator account can
  also request creator access after the fact via a button on
  `/lesson-creator` (`POST /account/request-creator`), not just at
  signup. `db.py`'s migration carries forward anyone who had the old
  `role='educator'` allowlist access as `account_type='creator',
  creator_status='verified'`, tested against a simulated old-schema
  database. `current_user.can_create_lessons` (account_type='creator'
  AND creator_status='verified') is the one gate that matters now;
  `current_user.is_admin` is computed at request time from
  `ADMIN_EMAILS`, no DB column needed.
- **Lesson Creator, fully made — done.** Beyond v1's create-only form:
  **edit**, **unpublish/republish**, and **delete** for your own
  lessons (`PUT`/`DELETE /api/lessons/<id>`, `POST
  /api/lessons/<id>/publish`), all ownership-checked server-side (a
  non-owner's edit attempt gets a real `403`, tested). An unpublished
  lesson is still visible to its own author (for preview) but 404s for
  everyone else. `/lesson-creator` now has distinct states for every
  combination of signed-out / wrong account type / pending / rejected
  / verified, instead of just "educator or not."
- **Prev/Next lesson navigation — done.** A `LESSON_ORDER` list +
  `_lesson_nav()` helper in `app.py`, and a shared Jinja macro
  (`templates/_lesson_nav.html`) rendering at the top and bottom of
  every built-in lesson. Verified the actual link targets at every
  point in the sequence, not just that the nav renders.
- **Hardware Lab — real content, done.** The three planned sections
  are built: a MOSFET cross-section (the classical baseline), an
  animated LC-loop energy-decay demo (drag resistance to zero and it
  stops decaying — the same mechanism a superconducting qubit's loop
  uses), and a clickable chip-layout diagram (capacitor pads,
  Josephson junction, meandering resonator, feedline) as the
  promised "actual chip layout" version of Physical Qubit's labeled
  boxes. Now Lesson 4 in the sequence (Reality Check renumbered to
  Lesson 5 to make room), with real step-checkbox progress tracking
  like every other lesson.
- **A real code editor — done, deliberately restricted.** `/api/run-
  code` accepts arbitrary-looking Python but validates it with an AST
  walker before ever calling `exec()` — only `QuantumCircuit`
  construction, a fixed gate/measure method allowlist, simple variable
  assignment, and basic arithmetic are permitted; no imports, no
  loops, no function/class definitions, no attribute access starting
  with `__` anywhere in the tree (closes the classic
  `().__class__.__bases__...` sandbox-escape pattern, which doesn't
  even need a dangerous *call* to work). No loops in the grammar also
  means there's structurally no way to write an infinite loop, on top
  of a `SIGALRM`-based 3-second wall-clock timeout as defense in
  depth. Tested against 18 separate attack vectors (import, eval,
  dunder access, the classic subclasses() escape, loops, function
  defs, resource limits) — all correctly rejected with no server
  errors. Caught and fixed a real bug while testing: the
  "did they add a measurement" check only looked at whether classical
  bits were *allocated*, not whether `.measure()` was actually
  *called* — a circuit with unused clbits crashed with an unhandled
  500 instead of a clean 400; fixed to check for an actual measure
  instruction in the circuit. Every fixed snippet and the Circuit
  Builder now has an "Open in editor →" button that loads the
  restricted-grammar equivalent (stripped of the illustrative
  imports/`print()` those code blocks show) into the editor.
- **Step-checkbox progress tracking on custom lessons — done.**
  `custom-lesson.html` now renders the same checkboxes + progress bar
  as every built-in lesson, keyed as `custom-<slug>` so it can't
  collide with the 6 fixed lesson ids. `app.py`'s progress endpoints
  now call a new `_is_valid_lesson_id()` instead of a flat
  `VALID_LESSON_IDS` membership check — true for the 6 built-ins, or
  for `custom-<slug>` where that slug is a currently-*published*
  lesson (unpublishing one blocks new progress writes against it,
  tested — existing rows aren't deleted, just orphaned harmlessly).
  Reuses `initLessonProgress()`/`window.QS_AUTHENTICATED` as-is, so
  it's signed-in-only tracking on an otherwise-open page, same as
  QM Basics and Single Qubit.

## Recently shipped (earlier rounds)

- **Qiskit Aer comparison** — `/api/compare-shots` in `app.py` runs the
  visitor's current single-qubit circuit through real `qiskit-aer` and
  returns counts. Single Qubit's Step 5 calls it ("your sandbox" vs.
  "Qiskit Aer" side by side); **Python IDE now calls it too** (see
  below). `qiskit`/`qiskit-aer` are in `requirements.txt`, imported
  lazily in `app.py` so the rest of the app still boots without them
  (the endpoint returns a 501 with a clear message instead).
- **Favicon** — `static/images/logo.svg` (+ generated `favicon.ico`,
  `apple-touch-icon.png`, and 192/512px PWA icons) is the same atom
  mark used in the sidebar brand.
- **Lesson 0 · QM Basics** — `/qm-basics`. State vectors, Born's rule
  via a live α-slider, and a normalization sandbox. Open access, listed
  first on `/lessons`, linked from Single Qubit's Step 1.
- **Real accounts (was #10) — done.** Google OAuth via Authlib +
  server-side sessions via Flask-Login, backed by a small SQLite
  database (`db.py`: a `users` table and a `lesson_progress` table).
  The old localStorage-only mock (`static/js/auth.js`) is deleted.
  Two Qubits, Physical Qubit, Hardware Lab, Reality Check, and Account
  are `@login_required` routes now — anonymous visitors are actually
  redirected to `/login?next=...` server-side (verified: `curl`
  returns a real `302`, not a client-side hide). QM Basics, Single
  Qubit, and everything under `/demos`/`/sandbox` stay open. Per-lesson
  progress (checkboxes + last-visited timestamps) is now real
  server-side data via `/api/progress*` in `app.py`, keyed by account,
  not by browser — `lesson-progress.js` was rewritten around `fetch()`
  instead of `localStorage`. Google sign-in needs real credentials
  (`GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` — see `.env.example`).
  What's deliberately **not** migrated: usage stats (shots run/gates
  applied, `stats.js`) stay local-per-browser — cosmetic counters, not
  account data, and migrating them would mean either a network call
  per gate click or a batching layer; a reasonable follow-up, not core
  to "real accounts."
- **CSRF protection + account deletion (#10 follow-ups) — done.** A
  lightweight double-submit CSRF token (`session['csrf_token']`,
  handed to the frontend as `window.QS_CSRF_TOKEN` via `base.html`,
  required as an `X-CSRF-Token` header on every state-changing POST —
  no `Flask-WTF` dependency needed) now guards
  `/api/progress/<id>/step`, `/visit`, `/api/lessons`, and
  `/account/delete`. Verified: missing or wrong token → `403`, correct
  token → normal behavior, GETs unaffected. `/account/delete` (real
  `POST`, confirm() dialog client-side, cascading + irreversible —
  deletes the user row, their lesson progress, and any lessons they
  authored) is live on the Account page's new "Danger zone" section.
- **Educator role (#10/#11) — done.** `users.role` (`'student'` |
  `'educator'`, migrated in for any pre-existing database via a
  `PRAGMA table_info` check in `db.py` — tested against a simulated
  old-schema DB). Granted via an `EDUCATOR_EMAILS` allowlist env var,
  checked only on real Google sign-in (`_maybe_grant_educator` in
  `app.py`) — Demo Guest accounts can never qualify, since there's no
  real email to verify. No admin UI to grant/revoke; that's a plain
  env var edit for now.
- **Lesson Creator v1 (#11) — done**, past the "coming soon" stub.
  `/lesson-creator` now has three real states depending on who's
  looking: signed-out gets the original pitch + a sign-in link;
  signed-in non-educators get a clear "allowlist, ask whoever's
  running this" message; **educators get a real authoring form** —
  title, description, up to 12 steps (each plain text + an optional
  embedded widget — reuses `/embed/coin-flip`/`/embed/two-qubit`
  rather than building lesson-authoring-specific widgets), submitted
  via `POST /api/lessons` to a new `custom_lessons` table (`db.py`).
  Published lessons render at `/lessons/custom/<slug>`
  (`custom-lesson.html`) — open to everyone, no sign-in needed to
  read, same as the built-in open lessons — and show up in a new
  "Community lessons" section on `/lessons`. Verified end-to-end: an
  educator session creates a lesson, an anonymous client can view it,
  it appears in the catalog, a non-educator's create attempt gets
  `403`, and a bogus slug gets a real `404`. **Deliberately not
  done:** step-checkbox progress tracking on custom lessons (v1 is
  read-only), rich text/markdown in step bodies (plain text only, by
  design — no HTML is accepted or rendered anywhere in this feature,
  so there's no stored-XSS surface even though this is
  user-submitted content shown to other users), and editing/
  unpublishing after the fact (publish is currently one-way).
- **Demos page** (`/demos`, open to everyone) — Demo 1 (Coin Flip,
  `/demos/coin-flip`, a working scaffold with a live Bloch sphere +
  flip/histogram widgets) and the Single Qubit lesson.
- **Sandbox** (`/sandbox`) — full-screen widgets (Bloch sphere,
  shot-runner, two-qubit basis-state picker) with no lesson scaffolding
  around them, reusing `quantum.js`/`twoqubit.js`/`bloch.js` as-is.
  Not in the sidebar nav (reached via a card on `/demos` and "Open
  full-screen →" links from lesson sandbox panels), matching the "reach
  lessons through cards, not sidebar rows" pattern used for lessons.
- **PWA support** — `static/manifest.json`, `static/js/sw.js` (service
  worker, precaches the actual current routes), registered in
  `base.html`/`landing.html`/`login.html`. Installable to a home
  screen; works offline for previously-visited pages.
- **Onboarding panel** — a dismissible orientation card on `/dashboard`
  for first-time visitors (points at the sidebar, QM Basics, sign-in).
  Dismiss state and "Start with Lesson 0" both persist via
  `localStorage` (`qs_onboarding_dismissed`); fully wired up, not just
  markup.
- **Sidebar restructured, twice.** First pass collapsed one row per
  lesson down to Dashboard/Demos/Lesson Creator/Python IDE. Second
  pass added **Lessons** (the full catalog, split back out of
  Dashboard — see below) and **Account** back in as their own rows,
  since both are permanent, not "lesson content." Current sidebar:
  Dashboard, Lessons, Demos, Lesson Creator, Python IDE, Account —
  Lesson Creator's "Soon" badge is gone now that v1 is real (see
  below), even though it's still access-gated for most visitors.
- **Dashboard vs. Lessons split** — `/dashboard` used to *be* the full
  lesson grid; it's now a personalized view: usage stats + a "Continue
  where you left off" list (up to 4 most-recently-visited, incomplete
  lessons, sorted by a new `qs_lesson_visits` localStorage timestamp —
  see `recordLessonVisit()`/`getLessonVisitTime()` in
  `lesson-progress.js`). Signed out, or signed in with nothing started,
  it shows an empty-state prompt instead. The full catalog (every
  lesson, gated ones shown locked) moved to the new `/lessons` route
  (`templates/lessons.html`) — essentially the old dashboard grid,
  relocated. `static/js/lessons-data.js` is a new small file holding
  `QS_LESSON_DEFS` (id/title/href/step-count/gated) as the one place
  that needs updating when a lesson's step count changes — Dashboard,
  Lessons, and Account all read from it now instead of each hardcoding
  their own copy.
- **Account page** (`/account`, `@login_required`) — real profile
  (name/email/avatar photo from `current_user`, server-rendered — no
  JS/localStorage involved), the same local usage stats as Dashboard,
  a real per-lesson progress list (pct + last-opened date, from
  `/api/progress`), and a real **Sign out** link (`/logout`, ends the
  Flask-Login session) — moved here from an inline sidebar-footer
  link, which now just says "Hi, Name →" and links to this page.
- **Python IDE v1 → v1.5** (`/python-ide`) — no longer a stub. Five
  real, runnable snippets: Hadamard, Pauli-X, tunable RY(θ) with a live
  degree slider (single-qubit, hits `/api/compare-shots`), plus **two
  new two-qubit snippets** — Prepare |11⟩ and a Bell state — hitting
  the new `/api/compare-shots-2q` endpoint (see below). Each gate
  mention links to the real Qiskit docs. Also new: a **Circuit
  Builder** — pick 1 or 2 qubits, click gates from a constrained
  palette (with hover/click descriptions) to build a circuit, watch
  real Python generate live, then run it against the same endpoints.
  Not a code editor — you can't type arbitrary Python, that's a
  separate, bigger decision (see #12) — but no longer stuck with five
  fixed presets either.
- **Two-qubit Qiskit comparison** (`/api/compare-shots-2q`) — sibling
  of `/api/compare-shots` for 2-qubit circuits (`X1`/`X2`/`H1`/`CNOT`,
  matching `twoqubit.js`'s gate set), returning real counts for all
  four basis states. Handles Qiskit's little-endian bit ordering
  internally so the frontend gets results in the same "q1 q2"
  left-to-right convention the lessons already use — see the comment
  in `app.py` if you're touching this, the ordering is easy to get
  backwards. Open to everyone, no login needed — not account data.
- **Embeddable widgets** (`/embed/coin-flip`, `/embed/two-qubit`) —
  chrome-less versions of the single-qubit and Bell-state widgets (no
  sidebar/topbar/footer, no restrictive frame headers) meant for
  `<iframe>`-ing into another site or course page. `demo-coin-flip.html`
  and `two-qubit.html` link to their respective embed page;
  `demo-coin-flip.html` also has a copy-pasteable `<iframe>` snippet.
  This is also the resolution to the old "should the duplicated
  widgets be consolidated" question — see #4 below for the reasoning.
- **Sandbox hash deep-links** — `/sandbox#bloch`, `#two`, `#physical`
  now work (alongside the existing `?topic=` query param), so a
  specific widget has its own shareable URL. Clicking a tab also
  updates the hash.

---

## 1. Dedicated Sandbox — further ideas

The `/sandbox` page itself is built, hash deep-links shipped
(`/sandbox#bloch`, `#two`, `#physical`), and both a single-qubit
(`/embed/coin-flip`) and two-qubit (`/embed/two-qubit`) embeddable
widget exist — see "Recently shipped." If a physical-qubit
(temperature/decoherence) embeddable version is wanted later, follow
the same pattern: a new chrome-less template + route, not a
modification to `/sandbox` itself (which has sidebar chrome and three
tabs, and doesn't suit iframing the way a single dedicated widget does).

## 2. Real photography / high-res imagery

This build only ships hand-built SVG illustrations and diagrams — no
network access in the build environment to fetch real photographs, and
fabricating "photos" would be dishonest about what they are. To add
real imagery later: drop licensed/royalty-free photos (dilution
refrigerator interiors, real chip photos — many published openly by
IBM/Google/Rigetti research blogs, check individual licensing) into
`static/images/`, reference normally via `url_for('static', ...)`.
Good candidates: `landing.html` hero, a real chip photo alongside the
schematic on `physical-qubit.html`.

## 3. Qiskit real-hardware toggle

Originally "Branch B": running the Single/Two Qubit sandboxes against
real IBM Quantum hardware via the IBM Quantum API, with a
"Simulated" vs. "Real hardware run" toggle, to make the real-world
noise theme concrete. Requires an IBM Quantum API key, network calls
from Flask, and realistically a job-queue/polling UI since real
hardware runs aren't instant. Bigger lift than the Qiskit Aer
comparison above — sequence after it and after #10 (real accounts, so
API usage can reasonably be rate-limited per user).

## 4. Consolidating Bloch sphere / shot-runner widgets — decided

**Decision:** don't merge the three existing copies (Single Qubit's
Steps 2–3, `demo-coin-flip.html`, `/sandbox`'s Single Qubit tab) into
one shared component. Each serves a genuinely different purpose —
lesson-embedded with narrative, a framed "heads/tails" marketing demo,
and a raw no-narrative playground — and since none of them share
runtime state (each instantiates its own `Qubit`/`createBlochWidget`),
there was no bug or maintenance cost being caused by the duplication,
only a mild "which one is the real one" ambiguity.

Instead, `/embed/coin-flip` (and `/embed/two-qubit` for the entangled
case — see "Recently shipped") is the answer to the actual underlying
need: a single, canonical, reusable, linkable version for anyone who
wants "just the widget" outside this app entirely (a course page, a
Notion doc, embedded elsewhere). The three-plus in-app copies stay as
they are. If a future session decides the in-app copies really should
collapse into one (e.g. Single Qubit's Step 2 literally `<iframe>`-ing
the embed version instead of duplicating the JS), that's still an open
call — but it's no longer blocking anything, since the actual "give me
a reusable widget" need now has a real answer.

## 10. Real accounts — what's left

The core (OAuth, sessions, CSRF, account deletion) plus the account-
type/creator-verification system (student/educator/creator,
`/admin/creators`) are done — see "Recently shipped." What's still
genuinely left:

- **Usage stats → backend.** `stats.js`'s shot/gate counters are still
  `localStorage`, intentionally not migrated (see "Recently shipped"
  for why — cosmetic counters, not account data).
- **Data export.** A user can delete their account now, but can't yet
  see/export what's stored about them beforehand. Small addition.
- **`SECRET_KEY` in production** — `app.py` falls back to an insecure
  dev default if the env var isn't set; fine on localhost, must be set
  explicitly (see `.env.example`) before deploying anywhere real.
- **Admin approvals have no notification.** `/admin/creators` works,
  but an admin has to remember to go check it — no email/notification
  tells them a request is waiting.
- **No self-serve re-request after rejection.** `creator_status=
  'rejected'` is a dead end today — `/lesson-creator` just explains
  it, no button to try again. Reasonable v1 cut, not obviously the
  right permanent answer.

## 11. Lesson Creator — what's left

Create, edit, publish/unpublish, delete, and step-checkbox progress
tracking are all done — see "Recently shipped." Left:

- **Progress not surfaced outside the lesson page itself** — Dashboard's
  "continue" list and Account's per-lesson list both only know about
  `QS_LESSON_DEFS` (the 6 built-in lessons); a custom lesson someone's
  part-way through won't show up there yet, even though the progress
  data exists (`/api/progress` already returns `custom-<slug>` keys —
  displaying them just needs a title lookup for whatever slugs turn up
  in that response).
- **Rich text / markdown** in step bodies — plain text only right now
  (a deliberate safety choice, not an oversight — see "Recently
  shipped"). Markdown would need a sanitizing renderer (e.g.
  `markdown` + `bleach`, not just `markdown` alone) before it's safe to
  add, since step bodies are shown to every visitor.
- **More widget choices** — the widget dropdown only offers the two
  existing embeds (Coin Flip, Two Qubit). A Physical Qubit embed (see
  #1 above) would need to be built first before it could be a third
  option here.
- **Version history** — editing overwrites in place, no way to see or
  revert to a previous version of a lesson.

## 12. Python IDE — remaining scope

The real, AST-restricted code editor shipped this round — see
"Recently shipped." Left:

- **Loops, in some safe form.** The current grammar has none at all
  (see "Recently shipped" for why that was the simplest safe choice
  for v1) — a bounded `for i in range(N)` with N capped small might be
  addable later without reopening the hang risk, but needs its own
  careful thought about what "bounded" actually guarantees once
  nested.
- **More two-qubit snippets/gates in the Circuit Builder** — the
  builder only exposes `X1`/`X2`/`H1`/`CNOT`, matching what
  `/api/compare-shots-2q` accepts. A second CNOT direction (control
  qubit 2, target qubit 1) or single-qubit gates addressable to either
  qubit (not just qubit 1) would need both a backend extension and a
  slightly less trivial gate-string format than the current flat list.
- **Doc links beyond the gate methods** — currently link each
  `.h()`/`.x()`/`.ry()`/`.cx()` mention to the general `QuantumCircuit`
  API page (a specific per-method anchor wasn't reliably verifiable —
  see the comment left where these links are defined in
  `python-ide.html` if extending this).
- **Saved/shareable circuits** — the editor's content is lost on
  refresh; no way to save a circuit you wrote or share a link to it,
  the way custom lessons have permanent URLs.

---

## Suggested order if picking this back up

1. Surface custom-lesson progress on Dashboard/Account (#11) — small,
   the data already exists, just needs a title lookup and a bit of UI.
2. Real photography (#2) and a bounded-loop story for the code editor
   (#12) as time allows.
3. Qiskit real-hardware toggle (#3) is the biggest remaining lift on
   its own (IBM Quantum API key, job-queue/polling UI). Smaller #10/
   #11 follow-ups (data export, admin notifications, version history)
   whenever convenient — none are urgent at this app's scale.
