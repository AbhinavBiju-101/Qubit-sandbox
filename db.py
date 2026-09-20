"""
db.py — Postgres (Supabase) persistence layer for real accounts.

Migrated from SQLite (see git history for the pre-migration version)
once the data outgrew what a single-file, single-writer SQLite DB
comfortably handles — SQLite's whole-database write lock becomes a
real bottleneck once you have concurrent app instances/workers, and a
single file on local disk doesn't survive a redeploy on most hosts
without a mounted volume. Supabase is just managed Postgres underneath
(plus auth/storage/etc. this app doesn't use) — connecting is a normal
`psycopg2` connection to a Postgres connection string, not a special
SDK, so nearly every query below is unchanged SQL.

No ORM on purpose, same reasoning as before the migration: this is a
couple dozen small tables and queries, SQLAlchemy would be more
ceremony than the app needs. To keep the migration itself low-risk,
`get_db()` returns a thin wrapper (`_PGConn`) whose `.execute(sql,
params)` mimics sqlite3's connection-level `.execute()` — most
functions below are completely unchanged from the SQLite version;
what *did* need real changes, function by function, was:
  - `?` placeholders -> `%s` (handled automatically by `_PGConn.execute`)
  - `cur.lastrowid` (SQLite-only) -> `INSERT ... RETURNING id` + `.lastrowid`
    property on the wrapper that reads it off the RETURNING row
  - `INSERT OR IGNORE` -> `INSERT ... ON CONFLICT (...) DO NOTHING`
  - `PRAGMA table_info(...)` (used for idempotent migrations) ->
    `information_schema.columns`
  - `INTEGER PRIMARY KEY AUTOINCREMENT` -> `SERIAL PRIMARY KEY`
Row access (`row["col"]`) is unchanged throughout — `psycopg2.extras.
RealDictCursor` (set in `_PGConn.execute`) returns dict-like rows, the
same ergonomics `sqlite3.Row` had.

Connects via a small connection pool (`psycopg2.pool`), one connection
checked out per request (`flask.g`, same lifecycle as before) and
returned (not closed) on teardown — cheap enough for this app's
traffic, and avoids a fresh TCP+TLS handshake to Supabase on every
request, which SQLite obviously never needed since it was a local file.

Required environment variable: DATABASE_URL (or SUPABASE_DB_URL as a
fallback name) — the Postgres connection string from Supabase's
dashboard: Project Settings -> Database -> Connection string -> URI.
Use the **direct connection** string (port 5432), not the pgbouncer
transaction-pooler string (port 6543) — this app holds a small pool of
long-lived connections itself (see above), which is exactly the
pattern the pooler string is meant to replace for serverless/
short-lived-function deploys; mixing the two just adds a second,
redundant pooling layer. If you deploy this as serverless functions
instead of a long-running process, switch to the pooler string AND
drop the pool size down to 1 (see register_app below).

Account types (futureplans.md #10/#11): every user picks one at signup
—  'student' (default, instant), 'educator' (instant, just a label —
no extra permissions beyond student today), or 'creator' (needs
verification — see `creator_status` — before Lesson Creator access is
actually granted). The older 'student'/'educator' `role` column from
before this model existed is kept in the schema (harmless) but no
longer read by app.py; `account_type`/`creator_status` are what matter
now. `_migrate()` below carries old `role='educator'` users forward as
`account_type='creator', creator_status='verified'` so nobody who had
Lesson Creator access loses it silently.

Usage from app.py:
    import db
    db.register_app(app)   # once, at startup — creates/migrates tables
    ...
    db.get_or_create_user(...)
    db.get_all_progress(user_id)
    db.set_step(user_id, lesson_id, step_id, done)
    db.record_visit(user_id, lesson_id)
    db.set_account_type(user_id, 'creator')
    db.set_creator_status(user_id, 'verified')
    db.create_custom_lesson(...)
    db.delete_user(user_id)
"""

import json
import os
import re
import secrets
import time

import psycopg2
import psycopg2.extras
import psycopg2.pool

from flask import g

_POOL = None  # set once by register_app()


class _PGConn:
    """Thin wrapper so the rest of this file can keep calling
    `db.execute(sql, params).fetchone()` exactly like it did against
    sqlite3 — psycopg2 connections don't have a connection-level
    `.execute()` (you go through a cursor), so this adds one. Also
    auto-converts `?` placeholders to psycopg2's `%s` so none of the
    ~80 queries below needed hand-editing for that alone."""

    def __init__(self, raw_conn):
        self.raw = raw_conn

    def execute(self, sql, params=()):
        cur = self.raw.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql.replace("?", "%s"), tuple(params))
        return _PGCursor(cur)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()


class _PGCursor:
    """Wraps a psycopg2 cursor; adds `.lastrowid`, reading it off an
    `INSERT ... RETURNING id` row (SQLite's cur.lastrowid has no
    Postgres equivalent — every INSERT that used it below now has an
    explicit RETURNING id clause instead)."""

    def __init__(self, cur):
        self._cur = cur

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def lastrowid(self):
        row = self._cur.fetchone()
        return row["id"] if row else None


def get_db():
    """Per-request connection (checked out of the pool), stashed on
    flask.g. Call only inside an app/request context (which is always
    true from route handlers)."""
    if "db" not in g:
        g.db = _PGConn(_POOL.getconn())
    return g.db


def close_db(e=None):
    """Returns the connection to the pool rather than closing it
    outright. Always rolls back first: if the request errored out
    mid-transaction, a pooled connection with a dangling failed
    transaction would poison the NEXT request that checks it out
    (Postgres refuses further queries on an aborted transaction until
    it's rolled back) — rollback() is a harmless no-op if everything
    was already committed cleanly."""
    conn = g.pop("db", None)
    if conn is not None:
        try:
            conn.rollback()
        except Exception:
            pass
        _POOL.putconn(conn.raw)


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    provider TEXT NOT NULL,        -- 'google'
    provider_sub TEXT NOT NULL,    -- Google's stable 'sub' claim
    email TEXT,
    name TEXT,
    avatar_url TEXT,
    role TEXT NOT NULL DEFAULT 'student',   -- legacy, no longer read by app.py — see account_type
    account_type TEXT NOT NULL DEFAULT 'student',  -- 'student' | 'educator' | 'creator'
    creator_status TEXT,           -- NULL | 'pending' | 'verified' | 'rejected' — only meaningful if account_type='creator'
    created_at INTEGER NOT NULL,
    UNIQUE(provider, provider_sub)
);

CREATE TABLE IF NOT EXISTS lesson_progress (
    user_id INTEGER NOT NULL REFERENCES users(id),
    lesson_id TEXT NOT NULL,
    done_steps TEXT NOT NULL DEFAULT '[]',   -- JSON array of step ids, e.g. ["step1","step2"]
    last_visited INTEGER,
    PRIMARY KEY (user_id, lesson_id)
);

-- Modules (scaling past a flat lesson list): a named, ordered
-- collection of lessons. author_user_id IS NULL for the one built-in
-- system module ("Module 1", seeded by _migrate() below, holding the
-- 6 original built-in lessons + the two embeddable widgets) — every
-- other row is a creator-authored module holding a subset of that
-- creator's own custom_lessons, published together as a set.
-- Created before custom_lessons below since custom_lessons.module_id
-- references it — Postgres validates FK target tables exist at
-- CREATE TABLE time, unlike SQLite which only checks at DML time, so
-- table creation order in this file actually matters here.
CREATE TABLE IF NOT EXISTS modules (
    id SERIAL PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT,
    author_user_id INTEGER REFERENCES users(id),  -- NULL = built-in system module
    published INTEGER NOT NULL DEFAULT 0,
    order_index INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS custom_lessons (
    id SERIAL PRIMARY KEY,
    author_user_id INTEGER NOT NULL REFERENCES users(id),
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT,
    steps_json TEXT NOT NULL DEFAULT '[]',   -- JSON array of {title, body, widget, checklist}
    published INTEGER NOT NULL DEFAULT 1,
    module_id INTEGER REFERENCES modules(id),
    preview_token TEXT,                      -- unguessable link to view while unpublished (draft mode)
    forked_from_id INTEGER REFERENCES custom_lessons(id),  -- set when created via "Fork this lesson"
    created_at INTEGER NOT NULL
);

-- Creator-built widgets (Lesson Creator + Python IDE crossover): a
-- named, saved restricted-grammar circuit (validated with the exact
-- same _validate_circuit_code() AST-walker /api/run-code uses — see
-- app.py) that a creator can drop into a lesson step instead of only
-- the two fixed embeds (coin-flip, two-qubit). Rendered read-only with
-- a "Run" button hitting /api/run-code with the saved code — no new
-- execution surface, same restricted grammar and sandboxing.
CREATE TABLE IF NOT EXISTS custom_widgets (
    id SERIAL PRIMARY KEY,
    author_user_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    code TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

-- Gamification: one row per user per UTC day they were active
-- (`record_activity` upserts, called by a periodic /api/activity/ping
-- while a lesson/demo/IDE page is open+focused — see app.py/static JS).
-- Powers streaks, the weekend badge, and the 40-hours badge. Minutes
-- are a coarse heartbeat count, not a precise timer — fine for badges.
CREATE TABLE IF NOT EXISTS activity_log (
    user_id INTEGER NOT NULL REFERENCES users(id),
    activity_date TEXT NOT NULL,   -- 'YYYY-MM-DD', UTC
    minutes INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, activity_date)
);

-- Badges are computed on demand (see compute_and_sync_badges below)
-- from activity_log + lesson_progress, but earned_at is persisted here
-- the first time a badge is earned so it doesn't move around if
-- later data changes (e.g. a streak later breaks).
CREATE TABLE IF NOT EXISTS badges (
    user_id INTEGER NOT NULL REFERENCES users(id),
    badge_key TEXT NOT NULL,
    earned_at INTEGER NOT NULL,
    PRIMARY KEY (user_id, badge_key)
);

-- Shareable circuits (anonymous-visitor branch): a permanent link to
-- one restricted-grammar snippet (same grammar/validator as
-- /api/run-code and custom widgets). author_user_id is NULL for an
-- anonymous share (no account needed to build and share something).
-- `public` opts a share into the /gallery listing; a share is always
-- viewable directly by its hash regardless of `public` — that flag
-- only controls whether it's *discoverable* by browsing, not whether
-- the link works, matching how an unlisted YouTube video behaves.
CREATE TABLE IF NOT EXISTS shared_circuits (
    id SERIAL PRIMARY KEY,
    hash TEXT NOT NULL UNIQUE,
    title TEXT,
    code TEXT NOT NULL,
    author_user_id INTEGER REFERENCES users(id),
    public INTEGER NOT NULL DEFAULT 0,
    view_count INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);

-- "Confused here" button (student-learning branch): a lightweight,
-- no-routing-anywhere signal. lesson_id is the same string key
-- progress uses (a built-in id like "single-qubit", or "custom-<slug>")
-- so this works on every lesson type without per-type wiring — see
-- the generic hookup in lesson-progress.js. user_id is nullable (an
-- anonymous visitor on an open lesson can still flag confusion).
CREATE TABLE IF NOT EXISTS step_confusion_reports (
    id SERIAL PRIMARY KEY,
    lesson_id TEXT NOT NULL,
    step_key TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id),
    created_at INTEGER NOT NULL
);
"""


def _migrate(conn):
    """Handles schema changes made after the initial release — safe to
    call on every startup, checks what's there before altering anything.
    `CREATE TABLE IF NOT EXISTS` above only covers brand-new databases;
    a database from an earlier version needs explicit ALTER TABLEs to
    pick up new columns. `conn` is a `_PGConn`-wrapped connection, same
    as everywhere else in this file — column existence is checked via
    `information_schema.columns` (Postgres) instead of SQLite's
    `PRAGMA table_info(...)`."""

    def _cols(table_name):
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?", (table_name,)
        ).fetchall()
        return {r["column_name"] for r in rows}

    cols = _cols("users")
    if "role" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'student'")
        conn.commit()
        cols.add("role")
    if "account_type" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN account_type TEXT NOT NULL DEFAULT 'student'")
        conn.execute("ALTER TABLE users ADD COLUMN creator_status TEXT")
        conn.commit()
        # Carry forward anyone who had the old role='educator' (the
        # original, allowlist-only Lesson Creator gate) so they don't
        # silently lose access under the new account_type model.
        conn.execute(
            "UPDATE users SET account_type = 'creator', creator_status = 'verified' WHERE role = 'educator'"
        )
        conn.commit()

    lesson_cols = _cols("custom_lessons")
    if lesson_cols and "module_id" not in lesson_cols:
        conn.execute("ALTER TABLE custom_lessons ADD COLUMN module_id INTEGER REFERENCES modules(id)")
        conn.commit()
    if lesson_cols and "preview_token" not in lesson_cols:
        conn.execute("ALTER TABLE custom_lessons ADD COLUMN preview_token TEXT")
        conn.commit()
    if lesson_cols and "forked_from_id" not in lesson_cols:
        conn.execute("ALTER TABLE custom_lessons ADD COLUMN forked_from_id INTEGER REFERENCES custom_lessons(id)")
        conn.commit()

    # Seed the one built-in system module ("Module 1") if it doesn't
    # exist yet — author_user_id IS NULL marks it as built-in (see
    # `modules` table comment). Everything that already existed before
    # Modules shipped (the 6 built-in lessons + the two embeddable
    # widgets) conceptually lives inside this row; app.py's catalog
    # builder attaches them by convention (LESSON_ORDER), not a DB
    # join, since those lessons aren't DB rows.
    row = conn.execute("SELECT id FROM modules WHERE slug = 'module-1'").fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO modules (slug, title, description, author_user_id, published, order_index, created_at) "
            "VALUES ('module-1', 'Module 1: Foundations', "
            "'The original six lessons — state vectors through scaling limits — plus the two sandbox widgets.', "
            "NULL, 1, 0, ?)",
            (int(time.time()),),
        )
        conn.commit()


def register_app(app):
    """Call once at startup. Connects to Postgres (Supabase), creates/
    migrates tables if needed, and wires connection cleanup into
    Flask's request teardown.

    Reads DATABASE_URL (or SUPABASE_DB_URL) from the environment — see
    the module docstring above for exactly which connection string to
    use from the Supabase dashboard. Pool size (1-10) is sized for a
    single long-running app process with modest traffic; bump the
    upper bound if you're running multiple worker processes and start
    seeing "pool exhausted" errors under load, or switch to the
    pgbouncer pooler string + a pool of 1 if you move to a
    serverless/multi-instance deploy (see module docstring)."""
    global _POOL
    database_url = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL (or SUPABASE_DB_URL) environment variable is required. "
            "Get this from your Supabase project: Project Settings -> Database -> "
            "Connection string -> URI (use the direct/session connection string, "
            "port 5432, not the pgbouncer transaction-pooler string on 6543 — "
            "see the top of db.py for why)."
        )

    app.teardown_appcontext(close_db)

    _POOL = psycopg2.pool.SimpleConnectionPool(1, 10, dsn=database_url)

    raw = _POOL.getconn()
    conn = _PGConn(raw)
    try:
        conn.execute(SCHEMA)
        conn.commit()
        _migrate(conn)
    finally:
        _POOL.putconn(raw)


# --------------------------------------------------------------------
# Users
# --------------------------------------------------------------------

def get_user_by_id(user_id):
    return get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def get_or_create_user(provider, provider_sub, email=None, name=None, avatar_url=None):
    """Looks up a user by (provider, provider_sub); creates one if it
    doesn't exist yet. Refreshes email/name/avatar on every call so a
    returning Google user's profile stays current.

    Returns (row, was_created) — app.py's signup flow needs to know
    whether this is a brand-new account (apply the account type picked
    on /signup) or a returning one (ignore it; they already have a type)."""
    db = get_db()
    row = db.execute(
        "SELECT * FROM users WHERE provider = ? AND provider_sub = ?", (provider, provider_sub)
    ).fetchone()
    if row:
        db.execute(
            "UPDATE users SET email = ?, name = ?, avatar_url = ? WHERE id = ?",
            (email, name, avatar_url, row["id"]),
        )
        db.commit()
        return get_user_by_id(row["id"]), False

    cur = db.execute(
        "INSERT INTO users (provider, provider_sub, email, name, avatar_url, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?) RETURNING id",
        (provider, provider_sub, email, name, avatar_url, int(time.time())),
    )
    db.commit()
    return get_user_by_id(cur.lastrowid), True


def set_account_type(user_id, account_type):
    """account_type must be 'student', 'educator', or 'creator'. Called
    at signup (see app.py's /signup flow) — only ever applied to a
    freshly-created user, existing accounts keep whatever type they
    picked originally (no self-serve "change my account type" flow)."""
    if account_type not in ("student", "educator", "creator"):
        raise ValueError(f"invalid account_type: {account_type!r}")
    db = get_db()
    db.execute("UPDATE users SET account_type = ? WHERE id = ?", (account_type, user_id))
    db.commit()


def set_creator_status(user_id, status):
    """status must be 'pending', 'verified', or 'rejected'. Set to
    'pending' when a creator-type account is created; moved to
    'verified' either automatically (CREATOR_EMAILS allowlist match —
    see app.py) or by an admin via /admin/creators."""
    if status not in ("pending", "verified", "rejected"):
        raise ValueError(f"invalid creator_status: {status!r}")
    db = get_db()
    db.execute("UPDATE users SET creator_status = ? WHERE id = ?", (status, user_id))
    db.commit()


def list_pending_creators():
    """For /admin/creators — everyone who signed up as 'creator' and is
    still waiting on approval, oldest first (first come, first served)."""
    return get_db().execute(
        "SELECT * FROM users WHERE account_type = 'creator' AND creator_status = 'pending' "
        "ORDER BY created_at ASC"
    ).fetchall()


def delete_user(user_id):
    """Deletes a user and cleans up everything that references them,
    in dependency order (foreign keys are enforced — always, in
    Postgres; this was ALSO true before the Postgres migration whenever
    SQLite's `PRAGMA foreign_keys = ON` was set, so this was a latent
    bug even then — it just never got exercised by a user who'd
    authored a module/widget/shared circuit before being deleted).
    Content ownership after deletion:
      - lesson_progress, activity_log, badges: deleted outright (all
        strictly personal, nothing else references them)
      - custom_lessons, custom_widgets, modules they authored: deleted
        outright too (an account-deletion flow leaving orphaned public
        content around, attributed to a user who no longer exists,
        would be confusing)
      - shared_circuits, step_confusion_reports: anonymized (author_
        user_id / user_id set to NULL) rather than deleted — both
        tables already support a NULL author/user (an anonymous share,
        an anonymous confusion report), so this just moves the row
        into that same "anonymous" state instead of destroying data
        someone else might still be relying on (e.g. a shared link)
    Irreversible; the caller (app.py's /account/delete) is responsible
    for confirming intent before calling this."""
    db = get_db()
    db.execute("DELETE FROM lesson_progress WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM activity_log WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM badges WHERE user_id = ?", (user_id,))
    db.execute("UPDATE step_confusion_reports SET user_id = NULL WHERE user_id = ?", (user_id,))
    db.execute("UPDATE shared_circuits SET author_user_id = NULL WHERE author_user_id = ?", (user_id,))
    # Clear any OTHER user's fork attribution pointing at a lesson
    # this user is about to lose, so that delete doesn't itself fail
    # on custom_lessons.forked_from_id's foreign key.
    db.execute(
        "UPDATE custom_lessons SET forked_from_id = NULL "
        "WHERE forked_from_id IN (SELECT id FROM custom_lessons WHERE author_user_id = ?)",
        (user_id,),
    )
    db.execute("DELETE FROM custom_lessons WHERE author_user_id = ?", (user_id,))
    db.execute("DELETE FROM custom_widgets WHERE author_user_id = ?", (user_id,))
    # Same reasoning as the forked_from_id clear above, for modules —
    # nothing in the app actually lets a lesson reference another
    # user's module today, but the schema doesn't forbid it, so this
    # stays defensive rather than assuming that invariant holds.
    db.execute(
        "UPDATE custom_lessons SET module_id = NULL "
        "WHERE module_id IN (SELECT id FROM modules WHERE author_user_id = ?)",
        (user_id,),
    )
    db.execute("DELETE FROM modules WHERE author_user_id = ?", (user_id,))
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()


# --------------------------------------------------------------------
# Lesson progress
# --------------------------------------------------------------------

def get_all_progress(user_id):
    """{ lesson_id: { done: [step_id, ...], last_visited: epoch_seconds|None } }
    for every lesson this user has touched. Missing lessons just aren't
    keys in the dict — callers should treat that as 0%/never-visited."""
    rows = get_db().execute(
        "SELECT lesson_id, done_steps, last_visited FROM lesson_progress WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    return {
        r["lesson_id"]: {"done": json.loads(r["done_steps"]), "last_visited": r["last_visited"]}
        for r in rows
    }


def get_lesson_progress(user_id, lesson_id):
    row = get_db().execute(
        "SELECT done_steps, last_visited FROM lesson_progress WHERE user_id = ? AND lesson_id = ?",
        (user_id, lesson_id),
    ).fetchone()
    if not row:
        return {"done": [], "last_visited": None}
    return {"done": json.loads(row["done_steps"]), "last_visited": row["last_visited"]}


def set_step(user_id, lesson_id, step_id, done):
    """Marks one step done/not-done for this user+lesson, preserving
    whatever last_visited was already there. Returns the updated list
    of done step ids."""
    db = get_db()
    current = set(get_lesson_progress(user_id, lesson_id)["done"])
    if done:
        current.add(step_id)
    else:
        current.discard(step_id)
    done_list = sorted(current)
    db.execute(
        """
        INSERT INTO lesson_progress (user_id, lesson_id, done_steps, last_visited)
        VALUES (?, ?, ?, (SELECT last_visited FROM lesson_progress WHERE user_id = ? AND lesson_id = ?))
        ON CONFLICT(user_id, lesson_id) DO UPDATE SET done_steps = excluded.done_steps
        """,
        (user_id, lesson_id, json.dumps(done_list), user_id, lesson_id),
    )
    db.commit()
    return done_list


def record_visit(user_id, lesson_id):
    """Stamps 'now' as this user's last-visited time for a lesson,
    without touching done_steps. Powers Dashboard's "Continue where you
    left off" ordering and Account's "Last opened" dates."""
    db = get_db()
    now = int(time.time())
    db.execute(
        """
        INSERT INTO lesson_progress (user_id, lesson_id, done_steps, last_visited)
        VALUES (?, ?, '[]', ?)
        ON CONFLICT(user_id, lesson_id) DO UPDATE SET last_visited = excluded.last_visited
        """,
        (user_id, lesson_id, now),
    )
    db.commit()
    return now


# --------------------------------------------------------------------
# Custom lessons (Lesson Creator — futureplans.md #11)
# --------------------------------------------------------------------

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(title):
    """'My Cool Lesson!' -> 'my-cool-lesson'. Not cryptographically
    anything — just URL-safe. Caller (create_custom_lesson) handles
    collisions by appending -2, -3, etc."""
    s = _SLUG_RE.sub("-", title.strip().lower()).strip("-")
    return s or "lesson"


def create_custom_lesson(author_user_id, title, description, steps, module_id=None, published=True):
    """`steps` is a list of {"title", "body", "widget", "checklist"}
    dicts — `widget` is None, "coin-flip", "two-qubit", or
    "custom-<id>" (a creator's own saved widget — see custom_widgets).
    `checklist` is an optional list of extra plain-text checkbox
    prompts for that step, beyond the built-in "mark step complete"
    checkbox — each renders as its own progress-tracked checkbox.
    `published=False` creates a draft (see preview_token/draft mode —
    app.py generates and attaches a preview token right after this
    call when a draft is requested). Returns the created row.
    Auto-generates a unique slug from the title; does not let the
    author pick one directly, to avoid slug-squatting/collision-
    handling complexity in the UI for v1."""
    db = get_db()
    base_slug = slugify(title)
    slug = base_slug
    n = 2
    while db.execute("SELECT 1 FROM custom_lessons WHERE slug = ?", (slug,)).fetchone():
        slug = f"{base_slug}-{n}"
        n += 1
    cur = db.execute(
        "INSERT INTO custom_lessons (author_user_id, slug, title, description, steps_json, published, module_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
        (author_user_id, slug, title, description, json.dumps(steps), 1 if published else 0, module_id, int(time.time())),
    )
    db.commit()
    return get_custom_lesson_by_id(cur.lastrowid)


def get_custom_lesson_by_id(lesson_id):
    return get_db().execute("SELECT * FROM custom_lessons WHERE id = ?", (lesson_id,)).fetchone()


def get_custom_lesson(slug):
    return get_db().execute("SELECT * FROM custom_lessons WHERE slug = ?", (slug,)).fetchone()


def list_custom_lessons(published_only=True):
    """Newest first — used by /lessons to show community-authored
    lessons alongside the built-in ones."""
    q = "SELECT * FROM custom_lessons"
    if published_only:
        q += " WHERE published = 1"
    q += " ORDER BY created_at DESC"
    return get_db().execute(q).fetchall()


def list_custom_lessons_by_author(author_user_id):
    return get_db().execute(
        "SELECT * FROM custom_lessons WHERE author_user_id = ? ORDER BY created_at DESC",
        (author_user_id,),
    ).fetchall()


def update_custom_lesson(lesson_id, title, description, steps, module_id=None):
    """Edits an existing lesson in place — same slug, same URL. Caller
    (app.py) is responsible for checking the requester actually authored
    this lesson before calling."""
    db = get_db()
    db.execute(
        "UPDATE custom_lessons SET title = ?, description = ?, steps_json = ?, module_id = ? WHERE id = ?",
        (title, description, json.dumps(steps), module_id, lesson_id),
    )
    db.commit()
    return get_custom_lesson_by_id(lesson_id)


def set_lesson_published(lesson_id, published):
    db = get_db()
    db.execute("UPDATE custom_lessons SET published = ? WHERE id = ?", (1 if published else 0, lesson_id))
    db.commit()


def delete_custom_lesson(lesson_id):
    db = get_db()
    db.execute("DELETE FROM custom_lessons WHERE id = ?", (lesson_id,))
    db.commit()


def list_custom_lessons_by_module(module_id, published_only=True):
    q = "SELECT * FROM custom_lessons WHERE module_id = ?"
    if published_only:
        q += " AND published = 1"
    q += " ORDER BY created_at ASC"
    return get_db().execute(q, (module_id,)).fetchall()


# --------------------------------------------------------------------
# Modules (scaling past a flat lesson list — see `modules` table above)
# --------------------------------------------------------------------

def get_builtin_module():
    """The one system module ('Module 1'), seeded by _migrate()."""
    return get_db().execute("SELECT * FROM modules WHERE slug = 'module-1'").fetchone()


def get_module_by_id(module_id):
    return get_db().execute("SELECT * FROM modules WHERE id = ?", (module_id,)).fetchone()


def get_module(slug):
    return get_db().execute("SELECT * FROM modules WHERE slug = ?", (slug,)).fetchone()


def create_module(author_user_id, title, description):
    """Creates a new, unpublished creator module. Slug collisions are
    handled the same way create_custom_lesson does — append -2, -3..."""
    db = get_db()
    base_slug = slugify(title)
    slug = base_slug
    n = 2
    while db.execute("SELECT 1 FROM modules WHERE slug = ?", (slug,)).fetchone():
        slug = f"{base_slug}-{n}"
        n += 1
    order_index = db.execute("SELECT COALESCE(MAX(order_index), 0) + 1 AS n FROM modules").fetchone()["n"]
    cur = db.execute(
        "INSERT INTO modules (slug, title, description, author_user_id, published, order_index, created_at) "
        "VALUES (?, ?, ?, ?, 0, ?, ?) RETURNING id",
        (slug, title, description, author_user_id, order_index, int(time.time())),
    )
    db.commit()
    return get_module_by_id(cur.lastrowid)


def update_module(module_id, title, description):
    db = get_db()
    db.execute("UPDATE modules SET title = ?, description = ? WHERE id = ?", (title, description, module_id))
    db.commit()
    return get_module_by_id(module_id)


def list_modules_by_author(author_user_id):
    return get_db().execute(
        "SELECT * FROM modules WHERE author_user_id = ? ORDER BY created_at DESC", (author_user_id,)
    ).fetchall()


def list_published_community_modules():
    """Published creator modules (author_user_id NOT NULL) that have
    at least one published lesson in them — an empty or all-unpublished
    module clutters the catalog for no reason."""
    return get_db().execute(
        """
        SELECT m.* FROM modules m
        WHERE m.author_user_id IS NOT NULL AND m.published = 1
        AND EXISTS (SELECT 1 FROM custom_lessons cl WHERE cl.module_id = m.id AND cl.published = 1)
        ORDER BY m.order_index ASC, m.created_at ASC
        """
    ).fetchall()


def set_module_published(module_id, published, publish_lessons_too=True):
    """Publishing a module optionally bulk-publishes every lesson
    currently assigned to it too ('publish together', as requested) —
    unpublishing the module does NOT unpublish its lessons individually
    (a creator might just want the module grouping hidden for now while
    keeping the lessons themselves reachable directly)."""
    db = get_db()
    db.execute("UPDATE modules SET published = ? WHERE id = ?", (1 if published else 0, module_id))
    if published and publish_lessons_too:
        db.execute("UPDATE custom_lessons SET published = 1 WHERE module_id = ?", (module_id,))
    db.commit()


def delete_module(module_id):
    """Deletes the module row only — lessons that were in it are kept,
    just detached (module_id set back to NULL), not deleted."""
    db = get_db()
    db.execute("UPDATE custom_lessons SET module_id = NULL WHERE module_id = ?", (module_id,))
    db.execute("DELETE FROM modules WHERE id = ?", (module_id,))
    db.commit()


def set_lesson_module(lesson_id, module_id):
    """module_id may be None to detach a lesson back to 'standalone'."""
    db = get_db()
    db.execute("UPDATE custom_lessons SET module_id = ? WHERE id = ?", (module_id, lesson_id))
    db.commit()


# --------------------------------------------------------------------
# Custom widgets (Lesson Creator × Python IDE crossover)
# --------------------------------------------------------------------

def create_custom_widget(author_user_id, title, code):
    db = get_db()
    cur = db.execute(
        "INSERT INTO custom_widgets (author_user_id, title, code, created_at) VALUES (?, ?, ?, ?) RETURNING id",
        (author_user_id, title, code, int(time.time())),
    )
    db.commit()
    return get_custom_widget_by_id(cur.lastrowid)


def get_custom_widget_by_id(widget_id):
    return get_db().execute("SELECT * FROM custom_widgets WHERE id = ?", (widget_id,)).fetchone()


def list_custom_widgets_by_author(author_user_id):
    return get_db().execute(
        "SELECT * FROM custom_widgets WHERE author_user_id = ? ORDER BY created_at DESC", (author_user_id,)
    ).fetchall()


def delete_custom_widget(widget_id):
    db = get_db()
    db.execute("DELETE FROM custom_widgets WHERE id = ?", (widget_id,))
    db.commit()


# --------------------------------------------------------------------
# Gamification: daily activity, streaks, badges
# --------------------------------------------------------------------

def record_activity(user_id, date_str, minutes=1):
    """Upserts today's (UTC, caller-supplied as 'YYYY-MM-DD') activity
    row, adding `minutes` to whatever's already logged. Called by a
    periodic heartbeat (/api/activity/ping) while a lesson/demo/IDE
    page is open and focused — see lesson-progress.js — so this is an
    approximate "were you actively here" signal, not a precise timer."""
    db = get_db()
    db.execute(
        """
        INSERT INTO activity_log (user_id, activity_date, minutes) VALUES (?, ?, ?)
        ON CONFLICT(user_id, activity_date) DO UPDATE SET minutes = activity_log.minutes + excluded.minutes
        """,
        (user_id, date_str, minutes),
    )
    db.commit()


def get_activity_dates(user_id):
    """Sorted list of 'YYYY-MM-DD' strings this user has any logged
    activity on — the raw material streaks/badges are computed from."""
    rows = get_db().execute(
        "SELECT activity_date FROM activity_log WHERE user_id = ? ORDER BY activity_date ASC", (user_id,)
    ).fetchall()
    return [r["activity_date"] for r in rows]


def get_total_minutes(user_id):
    row = get_db().execute(
        "SELECT COALESCE(SUM(minutes), 0) AS total FROM activity_log WHERE user_id = ?", (user_id,)
    ).fetchone()
    return row["total"]


def get_user_badges(user_id):
    """{ badge_key: earned_at_epoch }"""
    rows = get_db().execute("SELECT badge_key, earned_at FROM badges WHERE user_id = ?", (user_id,)).fetchall()
    return {r["badge_key"]: r["earned_at"] for r in rows}


def award_badge_if_new(user_id, badge_key):
    """Idempotent — INSERT ... ON CONFLICT DO NOTHING keyed on
    (user_id, badge_key) (the table's primary key), so calling this
    repeatedly for a badge someone already has is a no-op and
    earned_at never moves. Returns True the first time (freshly
    earned), False if they already had it."""
    db = get_db()
    cur = db.execute(
        "INSERT INTO badges (user_id, badge_key, earned_at) VALUES (?, ?, ?) "
        "ON CONFLICT (user_id, badge_key) DO NOTHING",
        (user_id, badge_key, int(time.time())),
    )
    db.commit()
    return cur.rowcount > 0


# Badge catalog: (key, label, description, icon-ish emoji). Kept as
# plain data here (not a class) since app.py's compute_and_sync_badges
# is what actually decides who's earned what — this is just display
# metadata shared by the account page and the toast notification.
BADGE_CATALOG = {
    "streak-3":       {"label": "3-Day Streak",     "emoji": "🔥", "desc": "Studied 3 days in a row."},
    "streak-7":       {"label": "Week Warrior",      "emoji": "🗓️", "desc": "A full 7-day streak."},
    "streak-30":      {"label": "Month Master",      "emoji": "🏆", "desc": "A full 30-day streak."},
    "weekend-studier":{"label": "Weekend Studier",   "emoji": "🌤️", "desc": "Studied on a Saturday and Sunday."},
    "hours-10":       {"label": "10 Hours In",       "emoji": "⏱️", "desc": "10 total hours of study time logged."},
    "hours-40":       {"label": "40 Hour Club",      "emoji": "💪", "desc": "40 total hours of study time logged."},
    "first-lesson":   {"label": "First Steps",       "emoji": "🎯", "desc": "Completed your first lesson."},
    "five-lessons":   {"label": "Getting Serious",   "emoji": "📚", "desc": "Completed 5 lessons."},
    "module-1-done":  {"label": "Module 1 Complete", "emoji": "🎓", "desc": "Finished every lesson in Module 1."},
    "early-bird":     {"label": "Early Bird",        "emoji": "🌅", "desc": "Studied before 7am (your local time)."},
    "night-owl":      {"label": "Night Owl",         "emoji": "🦉", "desc": "Studied after 11pm (your local time)."},
}


# ======================================================================
# Shareable circuits + Playground gallery
# ======================================================================

def create_shared_circuit(code, title=None, author_user_id=None, public=False):
    """Generates a short, URL-safe hash (not sequential — an
    autoincrement id would let people enumerate other people's shares
    by just counting up) and stores the circuit under it. Anonymous
    shares are fully supported (author_user_id=None) — sharing
    something you built doesn't require an account."""
    db = get_db()
    h = secrets.token_urlsafe(6).rstrip("=-_")[:8] or secrets.token_hex(4)
    while db.execute("SELECT 1 FROM shared_circuits WHERE hash = ?", (h,)).fetchone():
        h = secrets.token_urlsafe(6).rstrip("=-_")[:8] or secrets.token_hex(4)
    db.execute(
        "INSERT INTO shared_circuits (hash, title, code, author_user_id, public, view_count, created_at) "
        "VALUES (?, ?, ?, ?, ?, 0, ?)",
        (h, title, code, author_user_id, 1 if public else 0, int(time.time())),
    )
    db.commit()
    return get_shared_circuit(h)


def get_shared_circuit(hash_):
    return get_db().execute("SELECT * FROM shared_circuits WHERE hash = ?", (hash_,)).fetchone()


def bump_shared_circuit_views(hash_):
    db = get_db()
    db.execute("UPDATE shared_circuits SET view_count = view_count + 1 WHERE hash = ?", (hash_,))
    db.commit()


def list_public_shared_circuits(limit=48):
    """Newest first — the /gallery listing. Only circuits explicitly
    marked public at share time; the hash still works for anyone with
    the direct link regardless of this flag (see `shared_circuits`
    table comment)."""
    return get_db().execute(
        "SELECT * FROM shared_circuits WHERE public = 1 ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()


# ======================================================================
# Lesson step-completion analytics (creator's own lessons only) —
# derived from existing lesson_progress rows rather than a separate
# tracking table: every step checkbox toggle already writes into
# `done_steps`, so "how many people reached step N" is just an
# aggregate query over data that exists for progress-tracking anyway,
# with no extra writes or new tracking surface needed.
# ======================================================================

def get_lesson_step_completion_counts(lesson_id):
    """{ step_key: distinct_user_count } for one lesson_id (e.g.
    "custom-bell-states-101") — counts, across every user who has ANY
    progress on this lesson, how many have each individual step key
    (a "stepN" or a "stepN-cM" checklist item) marked done. Aggregate
    only — no per-user data is exposed."""
    rows = get_db().execute(
        "SELECT done_steps FROM lesson_progress WHERE lesson_id = ?", (lesson_id,)
    ).fetchall()
    counts = {}
    total_visitors = len(rows)
    for r in rows:
        try:
            done = json.loads(r["done_steps"])
        except (TypeError, ValueError):
            done = []
        for step_key in done:
            counts[step_key] = counts.get(step_key, 0) + 1
    return counts, total_visitors


# ======================================================================
# "Confused here" step reports
# ======================================================================

def record_confusion_report(lesson_id, step_key, user_id=None):
    db = get_db()
    db.execute(
        "INSERT INTO step_confusion_reports (lesson_id, step_key, user_id, created_at) VALUES (?, ?, ?, ?)",
        (lesson_id, step_key, user_id, int(time.time())),
    )
    db.commit()


def get_confusion_counts(lesson_id):
    """{ step_key: count } for one lesson — used by creator analytics
    (only the lesson's own author sees this, enforced in app.py)."""
    rows = get_db().execute(
        "SELECT step_key, COUNT(*) AS n FROM step_confusion_reports WHERE lesson_id = ? GROUP BY step_key",
        (lesson_id,),
    ).fetchall()
    return {r["step_key"]: r["n"] for r in rows}


# ======================================================================
# Draft/preview mode + forking
# ======================================================================

def set_lesson_preview_token(lesson_id, token):
    """token=None clears it (e.g. once a lesson is published, the
    preview link is no longer the only way to see it, but it's left
    valid rather than invalidated — simplest behavior, and a preview
    link leaking is no worse than the lesson being published)."""
    db = get_db()
    db.execute("UPDATE custom_lessons SET preview_token = ? WHERE id = ?", (token, lesson_id))
    db.commit()


def get_custom_lesson_by_preview_token(slug, token):
    return get_db().execute(
        "SELECT * FROM custom_lessons WHERE slug = ? AND preview_token = ? AND preview_token IS NOT NULL",
        (slug, token),
    ).fetchone()


def fork_custom_lesson(source_lesson, new_author_user_id):
    """Clones a published lesson's content (title, description, steps —
    NOT its module, since the fork almost certainly doesn't belong to
    the new author's module) under the new author, published as a
    draft (published=0) so they can review/edit before it goes live,
    and records forked_from_id for attribution."""
    db = get_db()
    base_slug = slugify(f"{source_lesson['title']}-fork")
    slug = base_slug
    n = 2
    while db.execute("SELECT 1 FROM custom_lessons WHERE slug = ?", (slug,)).fetchone():
        slug = f"{base_slug}-{n}"
        n += 1
    cur = db.execute(
        "INSERT INTO custom_lessons (author_user_id, slug, title, description, steps_json, published, "
        "module_id, forked_from_id, created_at) VALUES (?, ?, ?, ?, ?, 0, NULL, ?, ?) RETURNING id",
        (
            new_author_user_id, slug, f"{source_lesson['title']} (fork)", source_lesson["description"],
            source_lesson["steps_json"], source_lesson["id"], int(time.time()),
        ),
    )
    db.commit()
    return get_custom_lesson_by_id(cur.lastrowid)
