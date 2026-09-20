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

CREATE TABLE IF NOT EXISTS custom_lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author_user_id INTEGER NOT NULL REFERENCES users(id),
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT,
    steps_json TEXT NOT NULL DEFAULT '[]',   -- JSON array of {title, body, widget, checklist}
    published INTEGER NOT NULL DEFAULT 1,
    module_id INTEGER REFERENCES modules(id),
    created_at INTEGER NOT NULL
);

-- Modules (scaling past a flat lesson list): a named, ordered
-- collection of lessons. author_user_id IS NULL for the one built-in
-- system module ("Module 1", seeded by _migrate() below, holding the
-- 6 original built-in lessons + the two embeddable widgets) — every
-- other row is a creator-authored module holding a subset of that
-- creator's own custom_lessons, published together as a set.
CREATE TABLE IF NOT EXISTS modules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT,
    author_user_id INTEGER REFERENCES users(id),  -- NULL = built-in system module
    published INTEGER NOT NULL DEFAULT 0,
    order_index INTEGER NOT NULL DEFAULT 0,
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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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

    lesson_cols = {row[1] for row in conn.execute("PRAGMA table_info(custom_lessons)")}
    if lesson_cols and "module_id" not in lesson_cols:
        conn.execute("ALTER TABLE custom_lessons ADD COLUMN module_id INTEGER REFERENCES modules(id)")
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


def create_custom_lesson(author_user_id, title, description, steps, module_id=None):
    """`steps` is a list of {"title", "body", "widget", "checklist"}
    dicts — `widget` is None, "coin-flip", "two-qubit", or
    "custom-<id>" (a creator's own saved widget — see custom_widgets).
    `checklist` is an optional list of extra plain-text checkbox
    prompts for that step, beyond the built-in "mark step complete"
    checkbox — each renders as its own progress-tracked checkbox.
    Returns the created row. Auto-generates a unique slug from the
    title; does not let the author pick one directly, to avoid
    slug-squatting/collision-handling complexity in the UI for v1."""
    db = get_db()
    base_slug = slugify(title)
    slug = base_slug
    n = 2
    while db.execute("SELECT 1 FROM custom_lessons WHERE slug = ?", (slug,)).fetchone():
        slug = f"{base_slug}-{n}"
        n += 1
    cur = db.execute(
        "INSERT INTO custom_lessons (author_user_id, slug, title, description, steps_json, published, module_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
        (author_user_id, slug, title, description, json.dumps(steps), module_id, int(time.time())),
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
    order_index = db.execute("SELECT COALESCE(MAX(order_index), 0) + 1 FROM modules").fetchone()[0]
    cur = db.execute(
        "INSERT INTO modules (slug, title, description, author_user_id, published, order_index, created_at) "
        "VALUES (?, ?, ?, ?, 0, ?, ?)",
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
        "INSERT INTO custom_widgets (author_user_id, title, code, created_at) VALUES (?, ?, ?, ?)",
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
        ON CONFLICT(user_id, activity_date) DO UPDATE SET minutes = minutes + excluded.minutes
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
    """Idempotent — INSERT OR IGNORE keyed on (user_id, badge_key), so
    calling this repeatedly for a badge someone already has is a no-op
    and earned_at never moves. Returns True the first time (freshly
    earned), False if they already had it."""
    db = get_db()
    cur = db.execute(
        "INSERT OR IGNORE INTO badges (user_id, badge_key, earned_at) VALUES (?, ?, ?)",
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
