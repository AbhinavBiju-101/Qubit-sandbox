"""
db.py — tiny SQLite persistence layer for real accounts.

Replaces the old localStorage-only mock (static/js/auth.js, deleted —
see futureplans.md #10). No ORM on purpose: this is a handful of small
tables and queries, SQLAlchemy would be more ceremony than the app
needs right now.

The database file lives in Flask's `instance/` folder (already
gitignored — see .gitignore) so it never accidentally gets committed
or shipped in the Docker image via COPY . . — actually it WILL get
copied into the image if it exists at build time, which is fine for a
demo (single-container, single SQLite file) but means restarting the
container from a fresh image resets accounts. Fine for now; a real
deploy would mount a volume for instance/ or move to a hosted DB.

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
import sqlite3
import time

from flask import g

_DB_PATH = None  # set once by register_app()


def get_db():
    """Per-request connection, stashed on flask.g. Call only inside an
    app/request context (which is always true from route handlers)."""
    if "db" not in g:
        g.db = sqlite3.connect(_DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,        -- 'google' | 'guest'
    provider_sub TEXT NOT NULL,    -- Google's stable 'sub' claim, or a random guest id
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

CREATE TABLE IF NOT EXISTS custom_lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author_user_id INTEGER NOT NULL REFERENCES users(id),
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT,
    steps_json TEXT NOT NULL DEFAULT '[]',   -- JSON array of {title, body, widget}
    published INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL
);
"""


def _migrate(conn):
    """Handles schema changes made after the initial release — safe to
    call on every startup, checks what's there before altering anything.
    `CREATE TABLE IF NOT EXISTS` above only covers brand-new databases;
    an `instance/qubit_sandbox.db` from an earlier version needs
    explicit ALTER TABLEs to pick up new columns."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
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


def register_app(app):
    """Call once at startup. Creates instance/ + the DB file/tables if
    they don't exist yet, and wires connection cleanup into Flask's
    request teardown."""
    global _DB_PATH
    os.makedirs(app.instance_path, exist_ok=True)
    _DB_PATH = os.path.join(app.instance_path, "qubit_sandbox.db")

    app.teardown_appcontext(close_db)

    conn = sqlite3.connect(_DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    _migrate(conn)
    conn.close()


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
        "VALUES (?, ?, ?, ?, ?, ?)",
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
    """Deletes a user and everything that references them: their
    lesson_progress rows, and any custom_lessons they authored (an
    account-deletion flow leaving orphaned public content around would
    be confusing, and PRAGMA foreign_keys=ON — set in get_db() — would
    block the users-row delete otherwise anyway unless dependents go
    first). Irreversible; the caller (app.py's /account/delete) is
    responsible for confirming intent before calling this."""
    db = get_db()
    db.execute("DELETE FROM lesson_progress WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM custom_lessons WHERE author_user_id = ?", (user_id,))
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


def create_custom_lesson(author_user_id, title, description, steps):
    """`steps` is a list of {"title": str, "body": str, "widget": str|None}
    dicts — `widget` is one of None, "coin-flip", "two-qubit" (embedded
    via <iframe src="/embed/...">, reusing the widgets built for
    futureplans.md #2/#5 rather than building lesson-authoring-specific
    ones). Returns the created row. Auto-generates a unique slug from
    the title; does not let the author pick one directly, to avoid
    slug-squatting/collision-handling complexity in the UI for v1."""
    db = get_db()
    base_slug = slugify(title)
    slug = base_slug
    n = 2
    while db.execute("SELECT 1 FROM custom_lessons WHERE slug = ?", (slug,)).fetchone():
        slug = f"{base_slug}-{n}"
        n += 1
    cur = db.execute(
        "INSERT INTO custom_lessons (author_user_id, slug, title, description, steps_json, published, created_at) "
        "VALUES (?, ?, ?, ?, ?, 1, ?)",
        (author_user_id, slug, title, description, json.dumps(steps), int(time.time())),
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


def update_custom_lesson(lesson_id, title, description, steps):
    """Edits an existing lesson in place — same slug, same URL. Caller
    (app.py) is responsible for checking the requester actually authored
    this lesson before calling."""
    db = get_db()
    db.execute(
        "UPDATE custom_lessons SET title = ?, description = ?, steps_json = ? WHERE id = ?",
        (title, description, json.dumps(steps), lesson_id),
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
