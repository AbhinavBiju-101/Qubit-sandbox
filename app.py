"""
Qubit Sandbox — Flask app

Run it with:
    python app.py

Then open http://localhost:5000 in a browser.

Accounts are now real (futureplans.md #10): Google OAuth via Authlib +
server-side sessions via Flask-Login, backed by a small SQLite database
(db.py) for users and per-account lesson progress. The old
localStorage-only mock (static/js/auth.js) is gone. `@login_required`
below is enforced *server-side* now — Two Qubits, Physical Qubit,
Hardware Lab, Reality Check, and Account actually redirect anonymous
visitors to /login, rather than just hiding content in the browser.

Google OAuth needs real credentials to work (GOOGLE_CLIENT_ID /
GOOGLE_CLIENT_SECRET env vars — see .env.example and README.md for how
to get them from Google Cloud Console). Without them, GOOGLE_OAUTH_
CONFIGURED is False and /login falls back to a "Continue as Demo
Guest" option (still a real server-side account, just not Google-
verified) so the app stays demoable before credentials are set up.

Nearly all the "quantum simulation" logic lives in static/js/ and runs
in the visitor's browser, not here. Python's job: match a URL to a
page, hand every page the same sidebar nav data via NAV_ITEMS, run
circuits through real IBM Qiskit for comparison, serve the account/
progress API, and handle login/logout.
"""

import ast
import json
import math
import os
import secrets
import signal
import uuid
from functools import wraps

# Auto-loads a local .env file (see .env.example) if python-dotenv is
# installed — it's in requirements.txt, but this is wrapped in a
# try/except so `python app.py` still works even without it (e.g. env
# vars set some other way, like a host's dashboard).
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from authlib.integrations.flask_client import OAuth
from flask import Flask, abort, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user

import db

app = Flask(__name__)

# SECRET_KEY signs the session cookie — required for Flask-Login to work
# at all. The dev fallback below is fine for `python app.py` on your own
# machine; set a real SECRET_KEY env var before deploying anywhere real,
# or every restart invalidates all sessions (mildly annoying) and a
# guessable key means sessions could be forged (actually bad).
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-insecure-secret-change-me")

db.register_app(app)

# Qiskit + qiskit-aer are optional/heavy — imported lazily so the rest of
# the app still runs (and `python app.py` still boots) even if a dev
# environment hasn't installed them yet. See futureplans.md.
try:
    from qiskit import QuantumCircuit
    from qiskit_aer import AerSimulator

    QISKIT_AVAILABLE = True
except ImportError:
    QISKIT_AVAILABLE = False


# ======================================================================
# Auth — Google OAuth (Authlib) + server sessions (Flask-Login)
# ======================================================================

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_OAUTH_CONFIGURED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)

# Creator verification (futureplans.md #10/#11). Two allowlists, both
# comma-separated real email addresses in env vars:
#   CREATOR_EMAILS — signing up as 'creator' with a matching, real
#     Google-verified email auto-verifies instantly. Anyone else who
#     picks 'creator' at signup goes to 'pending' and needs an admin
#     to approve them at /admin/creators.
#   ADMIN_EMAILS — can see/approve/reject pending creator requests at
#     /admin/creators. Computed at request time from current_user.email
#     (see User.is_admin below) rather than stored on the user row, so
#     granting/revoking admin access is just an env var + restart, no
#     migration needed.
# Neither ever applies to Demo Guest sign-ins — those emails are
# random (guest-xxx@guest.local), never Google-verified, so a guest
# session can request 'creator' (to demo the pending-approval state)
# but can never auto-verify or become admin.
CREATOR_EMAILS = {
    e.strip().lower() for e in os.environ.get("CREATOR_EMAILS", "").split(",") if e.strip()
}
ADMIN_EMAILS = {
    e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()
}


def _apply_signup_account_type(user_row, account_type):
    """Called only for a FRESHLY CREATED user (see get_or_create_user's
    was_created flag) right after signup, with whatever type they
    picked on /signup ('student' is the default already, so this is a
    no-op call for that case). 'creator' also sets creator_status —
    auto-'verified' if the email matches CREATOR_EMAILS (Google sign-in
    only; guest emails never match), otherwise 'pending'."""
    if account_type not in ("student", "educator", "creator"):
        account_type = "student"
    if account_type != "student":
        db.set_account_type(user_row["id"], account_type)
    if account_type == "creator":
        email = (user_row["email"] or "").lower()
        status = "verified" if (user_row["provider"] == "google" and email in CREATOR_EMAILS) else "pending"
        db.set_creator_status(user_row["id"], status)
    return db.get_user_by_id(user_row["id"])


oauth = OAuth(app)
if GOOGLE_OAUTH_CONFIGURED:
    oauth.register(
        name="google",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

login_manager = LoginManager()
login_manager.login_view = "login"  # where @login_required sends anonymous visitors
login_manager.login_message = None  # we don't render flashed messages anywhere; skip the default one
login_manager.init_app(app)


class User(UserMixin):
    """Thin wrapper Flask-Login wants around a `users` row. Flask-Login
    itself only needs .id / .is_authenticated / etc. (from UserMixin) —
    name/email/avatar_url/provider/account_type/creator_status are just
    convenience for templates (`current_user.name` etc. in Jinja)."""

    def __init__(self, row):
        self.id = str(row["id"])
        self.email = row["email"]
        self.name = row["name"] or (row["email"].split("@")[0] if row["email"] else "Account")
        self.avatar_url = row["avatar_url"]
        self.provider = row["provider"]
        self.account_type = row["account_type"]
        self.creator_status = row["creator_status"]

    @property
    def can_create_lessons(self):
        return self.account_type == "creator" and self.creator_status == "verified"

    @property
    def is_admin(self):
        return bool(self.email) and self.email.lower() in ADMIN_EMAILS


@login_manager.user_loader
def load_user(user_id):
    row = db.get_user_by_id(int(user_id))
    return User(row) if row else None


def _safe_next(raw):
    """Only ever redirect to a same-site path after login — never an
    absolute/external URL (open-redirect protection)."""
    if raw and raw.startswith("/") and not raw.startswith("//"):
        return raw
    return None


@app.route("/auth/google/login")
def google_login():
    if not GOOGLE_OAUTH_CONFIGURED:
        return redirect(url_for("login"))
    next_url = _safe_next(request.args.get("next"))
    if next_url:
        session["post_login_redirect"] = next_url
    # Set only when arriving from /signup (its buttons add ?type=...);
    # /login's buttons don't, so a first-time sign-in there just
    # defaults to 'student' — see google_callback below.
    signup_type = request.args.get("type")
    if signup_type in ("student", "educator", "creator"):
        session["signup_account_type"] = signup_type
    redirect_uri = url_for("google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@app.route("/auth/google/callback")
def google_callback():
    if not GOOGLE_OAUTH_CONFIGURED:
        return redirect(url_for("login"))
    token = oauth.google.authorize_access_token()
    userinfo = token.get("userinfo")
    if not userinfo:
        # Some OpenID providers don't inline userinfo in the token response —
        # fall back to Authlib's ID-token parsing.
        userinfo = oauth.google.parse_id_token(token)
    row, was_created = db.get_or_create_user(
        provider="google",
        provider_sub=userinfo["sub"],
        email=userinfo.get("email"),
        name=userinfo.get("name"),
        avatar_url=userinfo.get("picture"),
    )
    signup_type = session.pop("signup_account_type", None)
    if was_created and signup_type:
        row = _apply_signup_account_type(row, signup_type)
    login_user(User(row))
    next_url = session.pop("post_login_redirect", None)
    if not next_url and was_created and signup_type == "creator" and row["creator_status"] == "pending":
        next_url = url_for("lesson_creator")  # land somewhere that explains the pending state
    return redirect(next_url or url_for("dashboard"))


@app.route("/auth/demo-login")
def demo_login():
    """Local-testing / hackathon-before-credentials-exist fallback. Makes
    a real server-side account (real row in `users`, real session — not
    the old localStorage mock) but skips real Google verification. Each
    click mints a FRESH, isolated guest identity (random provider_sub)
    rather than sharing one demo row across every visitor — otherwise
    two people demoing this at once would see each other's progress.
    Also accepts ?type=... from /signup, same as the Google path —
    'creator' always lands 'pending' here (see _apply_signup_account_type:
    guest emails never match CREATOR_EMAILS), useful for demoing what
    the pending state looks like without a real Google account."""
    guest_sub = f"guest-{uuid.uuid4().hex[:12]}"
    row, was_created = db.get_or_create_user(
        provider="guest",
        provider_sub=guest_sub,
        email=f"{guest_sub}@guest.local",
        name="Demo Guest",
        avatar_url=None,
    )
    signup_type = request.args.get("type")
    if was_created and signup_type in ("student", "educator", "creator"):
        row = _apply_signup_account_type(row, signup_type)
    login_user(User(row))
    next_url = _safe_next(request.args.get("next"))
    return redirect(next_url or url_for("dashboard"))


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("landing"))


# ======================================================================
# CSRF protection (futureplans.md #10 follow-up)
# ======================================================================
# Lightweight, no Flask-WTF dependency: a random per-session token,
# handed to the frontend via a <meta> tag (see base.html), sent back on
# every state-changing fetch() as an X-CSRF-Token header (see
# lesson-progress.js / lesson-creator.html), checked here. This is the
# "double-submit" pattern — it works because a cross-site page can
# trigger a request with the browser's cookies attached, but can't read
# this app's DOM to discover the token to put in the header. GET
# requests are never protected (they shouldn't change state); the
# OAuth login flow has its own CSRF protection built into Authlib (the
# `state` parameter), unrelated to this token.


@app.before_request
def _ensure_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(20)


def csrf_protect(f):
    """Apply to POST/PUT/DELETE routes that change state. GETs pass
    through untouched even if this decorator is (harmlessly) present."""

    @wraps(f)
    def wrapper(*args, **kwargs):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            sent = request.headers.get("X-CSRF-Token")
            if not sent or sent != session.get("csrf_token"):
                return jsonify({"error": "csrf_failed", "message": "Missing or invalid CSRF token. Reload the page and try again."}), 403
        return f(*args, **kwargs)

    return wrapper


# ======================================================================
# Nav + pages
# ======================================================================

# Single source of truth for the sidebar. base.html loops over this,
# so adding a new top-level nav entry later is: add a route below + one
# entry here. Individual lessons (Two Qubits, Physical Qubit, Hardware
# Lab, Reality Check) intentionally do NOT get their own nav entries —
# they're reached through /lessons and /demos instead. Sandbox is the
# same story — reachable via a card on /demos and "Open full-screen"
# links from lesson pages, not its own row.
NAV_ITEMS = [
    {"key": "dashboard", "label": "Dashboard", "href": "/dashboard", "icon": "grid"},
    {"key": "lessons", "label": "Lessons", "href": "/lessons", "icon": "book"},
    {"key": "demos", "label": "Demos", "href": "/demos", "icon": "play"},
    {"key": "creator", "label": "Lesson Creator", "href": "/lesson-creator", "icon": "pencil"},
    {"key": "ide", "label": "Python IDE", "href": "/python-ide", "icon": "code"},
    {"key": "account", "label": "Account", "href": "/account", "icon": "user"},
]


# Canonical lesson sequence — powers the prev/next nav at the top and
# bottom of every lesson page (see templates/_lesson_nav.html). Order
# here IS the lesson order; reordering this list reorders the nav
# links everywhere, no per-template changes needed. Community
# (educator-authored) lessons aren't in this sequence — they're
# freestanding, no prev/next between them for v1.
LESSON_ORDER = [
    {"id": "qm-basics", "title": "QM Basics", "href": "/qm-basics"},
    {"id": "single-qubit", "title": "Single Qubit", "href": "/single-qubit"},
    {"id": "two-qubit", "title": "Two Qubits", "href": "/two-qubit"},
    {"id": "physical-qubit", "title": "Physical Qubit", "href": "/physical-qubit"},
    {"id": "hardware-lab", "title": "Hardware Lab", "href": "/hardware-lab"},
    {"id": "reality-check", "title": "Reality Check", "href": "/reality-check"},
]


def _lesson_nav(lesson_id):
    """Returns (prev_lesson, next_lesson) dicts (or None at either end
    of the sequence) for the given lesson id, per LESSON_ORDER above."""
    idx = next((i for i, l in enumerate(LESSON_ORDER) if l["id"] == lesson_id), None)
    if idx is None:
        return None, None
    prev_l = LESSON_ORDER[idx - 1] if idx > 0 else None
    next_l = LESSON_ORDER[idx + 1] if idx < len(LESSON_ORDER) - 1 else None
    return prev_l, next_l


@app.context_processor
def inject_nav():
    """Makes `nav_items`/`csrf_token` available in every template
    without passing them explicitly in each render_template() call
    below. `current_user` is already injected globally by Flask-Login."""
    return {"nav_items": NAV_ITEMS, "csrf_token": session.get("csrf_token", "")}


@app.route("/")
def landing():
    # Standalone marketing/introduction page — does NOT use the sidebar shell.
    return render_template("landing.html")


@app.route("/dashboard")
def dashboard():
    # Personalized landing page: onboarding panel (first visit), usage
    # stats (still local per-browser, see stats.js), and — for signed-in
    # visitors — a "continue where you left off" list built from the
    # real per-account progress API (/api/progress). The full lesson
    # catalog lives on /lessons instead.
    return render_template("dashboard.html", active_page="dashboard")


@app.route("/lessons")
def lessons():
    # The full lesson catalog — every built-in lesson (open or gated),
    # one card each, plus any published community-authored lessons
    # (see Lesson Creator / futureplans.md #11) in their own section.
    # Gated built-in lessons just show locked; clicking one while
    # signed out hits @login_required and bounces to /login.
    return render_template(
        "lessons.html", active_page="lessons", custom_lessons=db.list_custom_lessons()
    )


@app.route("/account")
@login_required
def account():
    # Real auth now (was a client-side mock): @login_required actually
    # redirects anonymous visitors to /login?next=/account, server-side.
    return render_template("account.html", active_page="account")


@app.route("/account/delete", methods=["POST"])
@login_required
@csrf_protect
def account_delete():
    """Deletes the signed-in user's row, their lesson progress, and any
    custom lessons they authored (see db.delete_user — this is a real,
    irreversible cascade, not a soft-delete). The confirmation step
    lives client-side (a JS confirm() dialog on the Account page,
    intentionally simple for this app's scale) — by the time this
    route runs, the request is trusted to mean it."""
    user_id = int(current_user.id)
    logout_user()
    db.delete_user(user_id)
    return redirect(url_for("landing"))


@app.route("/account/request-creator", methods=["POST"])
@login_required
@csrf_protect
def account_request_creator():
    """Lets an existing student/educator account request creator access
    after the fact — the signup-time picker (/signup) isn't the only
    way in, since someone might not know they'd want it until later.
    Same verification rule as signup: auto-'verified' if the email is
    Google-verified and in CREATOR_EMAILS, else 'pending' for admin
    review at /admin/creators."""
    if current_user.account_type == "creator":
        return jsonify({"account_type": "creator", "creator_status": current_user.creator_status})
    row = db.get_user_by_id(int(current_user.id))
    row = _apply_signup_account_type(row, "creator")
    return jsonify({"account_type": row["account_type"], "creator_status": row["creator_status"]})


@app.route("/demos")
def demos():
    # Open to everyone — this is the hackathon showcase page. Only
    # Single Qubit + Demo 1 (Coin Flip) live here for now.
    return render_template("demos.html", active_page="demos")


@app.route("/demos/coin-flip")
def demo_coin_flip():
    # Demo 1 — the coin flip simulator. Open to everyone, not gated.
    return render_template("demo-coin-flip.html", active_page="demos")


@app.route("/embed/coin-flip")
def embed_coin_flip():
    # Chrome-less version of the same widget (no sidebar/topbar/footer),
    # meant to be dropped into an <iframe> on someone else's site or a
    # course page. Deliberately does NOT set X-Frame-Options or a
    # restrictive frame-ancestors CSP — the whole point is to be
    # embeddable, so Flask's default (no framing restriction at all) is
    # what we want here. Open to everyone, like the rest of /demos —
    # nothing here is account data.
    return render_template("embed-coin-flip.html")


@app.route("/embed/two-qubit")
def embed_two_qubit():
    # Same pattern as /embed/coin-flip, for the Bell-state/entanglement
    # widget. No restrictive frame headers here either, same reasoning.
    return render_template("embed-two-qubit.html")


@app.route("/qm-basics")
def qm_basics():
    # Lesson 0 — open to everyone, same as Single Qubit.
    prev_l, next_l = _lesson_nav("qm-basics")
    return render_template("qm-basics.html", active_page="demos", prev_lesson=prev_l, next_lesson=next_l)


@app.route("/single-qubit")
def single_qubit():
    # Open to everyone — the one full lesson shown pre-signup.
    prev_l, next_l = _lesson_nav("single-qubit")
    return render_template("single-qubit.html", active_page="demos", prev_lesson=prev_l, next_lesson=next_l)


@app.route("/two-qubit")
@login_required
def two_qubit():
    prev_l, next_l = _lesson_nav("two-qubit")
    return render_template("two-qubit.html", active_page="lessons", prev_lesson=prev_l, next_lesson=next_l)


@app.route("/physical-qubit")
@login_required
def physical_qubit():
    prev_l, next_l = _lesson_nav("physical-qubit")
    return render_template("physical-qubit.html", active_page="lessons", prev_lesson=prev_l, next_lesson=next_l)


@app.route("/hardware-lab")
@login_required
def hardware_lab():
    prev_l, next_l = _lesson_nav("hardware-lab")
    return render_template("hardware-lab.html", active_page="lessons", prev_lesson=prev_l, next_lesson=next_l)


@app.route("/reality-check")
@login_required
def reality_check():
    prev_l, next_l = _lesson_nav("reality-check")
    return render_template("reality-check.html", active_page="lessons", prev_lesson=prev_l, next_lesson=next_l)


@app.route("/sandbox")
def sandbox():
    # Open to everyone, like Demos — a raw widget playground with no
    # lesson text and nothing to track, so it isn't gated even though
    # two of its three tabs mirror gated lessons. Supports both
    # ?topic=single|two|physical and #bloch/#two/#physical hash
    # deep-links (the tab also updates the hash on click, so the
    # current tab is a shareable URL).
    return render_template("sandbox.html", active_page="demos")


@app.route("/lesson-creator")
def lesson_creator():
    # v1 (futureplans.md #11): a real, working authoring form for
    # verified creator accounts (current_user.can_create_lessons — see
    # the account-type/CREATOR_EMAILS model above), rendered inside
    # lesson-creator.html itself via Jinja conditionals rather than a
    # separate template, since the signed-out / not-a-creator /
    # pending-approval states still need their own explanations.
    # Anyone's own past submissions are listed too (verified creators
    # only), via list_custom_lessons_by_author.
    my_lessons = []
    if current_user.is_authenticated and current_user.can_create_lessons:
        my_lessons = db.list_custom_lessons_by_author(int(current_user.id))
    return render_template("lesson-creator.html", active_page="creator", my_lessons=my_lessons)


def admin_required(f):
    """Like @login_required but also checks current_user.is_admin
    (ADMIN_EMAILS allowlist) — 403s rather than redirecting to /login,
    since the issue for an already-signed-in non-admin isn't "you need
    to sign in", it's "you don't have access"."""

    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("login", next=request.path))
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)

    return wrapper


@app.route("/admin/creators")
@admin_required
def admin_creators():
    return render_template(
        "admin-creators.html", active_page="admin", pending=db.list_pending_creators()
    )


@app.route("/admin/creators/<int:user_id>/approve", methods=["POST"])
@admin_required
@csrf_protect
def admin_approve_creator(user_id):
    row = db.get_user_by_id(user_id)
    if row is None or row["account_type"] != "creator":
        return jsonify({"error": "not_found"}), 404
    db.set_creator_status(user_id, "verified")
    return jsonify({"status": "verified"})


@app.route("/admin/creators/<int:user_id>/reject", methods=["POST"])
@admin_required
@csrf_protect
def admin_reject_creator(user_id):
    row = db.get_user_by_id(user_id)
    if row is None or row["account_type"] != "creator":
        return jsonify({"error": "not_found"}), 404
    db.set_creator_status(user_id, "rejected")
    return jsonify({"status": "rejected"})


MAX_LESSON_STEPS = 12
VALID_WIDGETS = {None, "coin-flip", "two-qubit"}


def _validate_lesson_payload(data):
    """Shared by create and edit. Returns (title, description, steps)
    on success, or (None, None, error_response) on failure — check
    `steps is None` to tell which case you got."""
    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    raw_steps = data.get("steps")

    if not title or len(title) > 200:
        return None, None, (jsonify({"error": "bad_request", "message": "Title is required (max 200 chars)."}), 400)
    if not isinstance(raw_steps, list) or not (1 <= len(raw_steps) <= MAX_LESSON_STEPS):
        return None, None, (jsonify({"error": "bad_request", "message": f"Need 1–{MAX_LESSON_STEPS} steps."}), 400)

    steps = []
    for s in raw_steps:
        if not isinstance(s, dict):
            return None, None, (jsonify({"error": "bad_request", "message": "Each step must be an object."}), 400)
        step_title = (s.get("title") or "").strip()
        body = (s.get("body") or "").strip()
        widget = s.get("widget") or None
        if not step_title or len(step_title) > 120:
            return None, None, (jsonify({"error": "bad_request", "message": "Each step needs a title (max 120 chars)."}), 400)
        if len(body) > 4000:
            return None, None, (jsonify({"error": "bad_request", "message": "Step body is too long (max 4000 chars)."}), 400)
        if widget not in VALID_WIDGETS:
            return None, None, (jsonify({"error": "bad_request", "message": f"Unknown widget: {widget!r}"}), 400)
        steps.append({"title": step_title, "body": body, "widget": widget})

    return title, description, steps


@app.route("/api/lessons", methods=["POST"])
@login_required
@csrf_protect
def api_create_lesson():
    """Creates a custom lesson — verified creator accounts only (403
    for everyone else, including regular signed-in students and
    creators still pending approval). Steps are plain text (rendered
    with Jinja's default autoescaping + CSS white-space:pre-line for
    linebreaks in custom-lesson.html — no raw HTML is accepted or
    rendered, so there's no stored-XSS surface here even though this is
    user-submitted content shown to other users)."""
    if not current_user.can_create_lessons:
        return jsonify({"error": "forbidden", "message": "Verified creator account required."}), 403

    data = request.get_json(silent=True) or {}
    title, description, steps = _validate_lesson_payload(data)
    if title is None:
        return steps  # _validate_lesson_payload stashed the (response, status) error tuple here on failure

    lesson = db.create_custom_lesson(int(current_user.id), title, description, steps)
    return jsonify({"slug": lesson["slug"], "url": url_for("custom_lesson", slug=lesson["slug"])})


def _get_own_lesson_or_403(lesson_id):
    """Shared ownership check for edit/publish-toggle/delete. Returns
    the lesson row, or None after already sending an error response —
    caller does `lesson = _get_own_lesson_or_403(id)` then
    `if lesson is None: return _last_error` (see call sites)."""
    lesson = db.get_custom_lesson_by_id(lesson_id)
    if lesson is None:
        return None, (jsonify({"error": "not_found"}), 404)
    if lesson["author_user_id"] != int(current_user.id):
        return None, (jsonify({"error": "forbidden", "message": "Not your lesson."}), 403)
    return lesson, None


@app.route("/api/lessons/<int:lesson_id>", methods=["PUT"])
@login_required
@csrf_protect
def api_edit_lesson(lesson_id):
    if not current_user.can_create_lessons:
        return jsonify({"error": "forbidden", "message": "Verified creator account required."}), 403
    lesson, err = _get_own_lesson_or_403(lesson_id)
    if lesson is None:
        return err

    data = request.get_json(silent=True) or {}
    title, description, steps = _validate_lesson_payload(data)
    if title is None:
        return steps

    updated = db.update_custom_lesson(lesson_id, title, description, steps)
    return jsonify({"slug": updated["slug"], "url": url_for("custom_lesson", slug=updated["slug"])})


@app.route("/api/lessons/<int:lesson_id>/publish", methods=["POST"])
@login_required
@csrf_protect
def api_toggle_publish_lesson(lesson_id):
    if not current_user.can_create_lessons:
        return jsonify({"error": "forbidden", "message": "Verified creator account required."}), 403
    lesson, err = _get_own_lesson_or_403(lesson_id)
    if lesson is None:
        return err
    data = request.get_json(silent=True) or {}
    published = bool(data.get("published"))
    db.set_lesson_published(lesson_id, published)
    return jsonify({"published": published})


@app.route("/api/lessons/<int:lesson_id>", methods=["DELETE"])
@login_required
@csrf_protect
def api_delete_lesson(lesson_id):
    if not current_user.can_create_lessons:
        return jsonify({"error": "forbidden", "message": "Verified creator account required."}), 403
    lesson, err = _get_own_lesson_or_403(lesson_id)
    if lesson is None:
        return err
    db.delete_custom_lesson(lesson_id)
    return jsonify({"deleted": True})


@app.route("/lessons/custom/<slug>")
def custom_lesson(slug):
    # Published custom lessons are open to everyone, same as the
    # built-in open lessons — no reason to gate community content
    # behind sign-in when QM Basics/Single Qubit aren't either. An
    # unpublished lesson is visible only to its own author (so they can
    # preview/edit it — see api_toggle_publish_lesson), 404 for anyone
    # else, same as a nonexistent slug (doesn't leak that it exists).
    # No step-checkbox progress tracking for v1 (would need
    # VALID_LESSON_IDS and the whole progress system to know about
    # dynamic lesson ids — a reasonable follow-up, not done here).
    lesson = db.get_custom_lesson(slug)
    if lesson is None:
        abort(404)
    is_own = current_user.is_authenticated and lesson["author_user_id"] == int(current_user.id)
    if not lesson["published"] and not is_own:
        abort(404)
    steps = json.loads(lesson["steps_json"])
    author = db.get_user_by_id(lesson["author_user_id"])
    return render_template(
        "custom-lesson.html",
        active_page="lessons",
        lesson=lesson,
        steps=steps,
        is_own=is_own,
        author_name=(author["name"] if author else "A Qubit Sandbox educator"),
    )


@app.route("/python-ide")
def python_ide():
    # v1.5: real, runnable Qiskit snippets — single-qubit (H/X/RY) plus
    # two-qubit (|11>, Bell state) against /api/compare-shots(-2q) — and
    # a Circuit Builder for composing a circuit from a constrained gate
    # palette instead of picking a fixed preset. Not a full code editor;
    # see futureplans.md #12 for why that's a deliberately separate,
    # bigger decision.
    return render_template("python-ide.html", active_page="ide")


@app.route("/login")
def login():
    if current_user.is_authenticated:
        return redirect(_safe_next(request.args.get("next")) or url_for("dashboard"))
    return render_template("login.html", google_oauth_configured=GOOGLE_OAUTH_CONFIGURED)


@app.route("/signup")
def signup():
    # Distinct from /login: this is where a NEW visitor picks an
    # account type (student/educator/creator) before authenticating.
    # The actual auth (Google or Demo Guest) is identical to /login's —
    # signup.html's buttons just add ?type=<picked> to the same
    # /auth/google/login and /auth/demo-login routes, which only apply
    # it if the resulting account is freshly created (see
    # google_callback/demo_login above). Returning users who land here
    # by mistake just get signed in normally, their existing type kept.
    if current_user.is_authenticated:
        return redirect(_safe_next(request.args.get("next")) or url_for("dashboard"))
    return render_template("signup.html", google_oauth_configured=GOOGLE_OAUTH_CONFIGURED)


@app.route("/sw.js")
def service_worker():
    # Served at the ROOT path deliberately — a service worker can only
    # control URLs at or below the path it's served from, and PWA scope
    # "/" (set in static/manifest.json) requires the script itself to
    # live at "/sw.js", not "/static/js/sw.js".
    response = send_from_directory("static/js", "sw.js")
    response.headers["Service-Worker-Allowed"] = "/"
    return response


# ======================================================================
# API — Qiskit comparison + real per-account progress
# ======================================================================

@app.route("/api/compare-shots", methods=["POST"])
def compare_shots():
    """Run the visitor's current single-qubit circuit through real IBM
    Qiskit (qiskit-aer's AerSimulator) and return measurement counts,
    so the frontend can show "your sandbox" vs. "Qiskit Aer" side by
    side. Open to everyone — not account data, doesn't need login.

    Body: { "gates": ["H", "X", ...] | ["RY:60"], "shots": 1000 }
    Gate strings mirror the labels the client-side Qubit class already
    logs (static/js/quantum.js), except RY is sent as "RY:<degrees>"
    since the client's own log string ("RY(60.0°)") isn't meant to be
    machine-parsed.
    """
    if not QISKIT_AVAILABLE:
        return (
            jsonify(
                {
                    "error": "qiskit_not_installed",
                    "message": (
                        "qiskit and qiskit-aer aren't installed on this server. "
                        "Run `pip install -r requirements.txt` (they're in there "
                        "now) and restart the app to enable this comparison."
                    ),
                }
            ),
            501,
        )

    data = request.get_json(silent=True) or {}
    gates = data.get("gates", [])
    if not isinstance(gates, list):
        return jsonify({"error": "bad_request", "message": "`gates` must be a list."}), 400

    shots = data.get("shots", 1000)
    try:
        shots = int(shots)
    except (TypeError, ValueError):
        shots = 1000
    shots = max(1, min(shots, 20000))  # sane upper bound, this runs synchronously

    qc = QuantumCircuit(1, 1)
    applied = []
    for gate in gates[:100]:  # sane upper bound on circuit depth for a demo endpoint
        if not isinstance(gate, str):
            continue
        if gate == "H":
            qc.h(0)
            applied.append("H")
        elif gate == "X":
            qc.x(0)
            applied.append("X")
        elif gate == "Y":
            qc.y(0)
            applied.append("Y")
        elif gate == "Z":
            qc.z(0)
            applied.append("Z")
        elif gate.startswith("RY:"):
            try:
                deg = float(gate.split(":", 1)[1])
            except ValueError:
                continue
            qc.ry(math.radians(deg), 0)
            applied.append(f"RY({deg:.1f}°)")
    qc.measure(0, 0)

    result = AerSimulator().run(qc, shots=shots).result()
    counts = result.get_counts()
    c0 = int(counts.get("0", 0))
    c1 = int(counts.get("1", 0))

    return jsonify(
        {
            "counts": {"0": c0, "1": c1},
            "shots": shots,
            "gates_applied": applied,
            "backend": "qiskit-aer AerSimulator",
        }
    )


@app.route("/api/compare-shots-2q", methods=["POST"])
def compare_shots_2q():
    """Two-qubit sibling of /api/compare-shots — used by Python IDE's
    two-qubit snippets and Circuit Builder. Runs a 2-qubit circuit
    through real qiskit-aer and returns counts for all four basis
    states. Open to everyone, same as /api/compare-shots.

    Body: { "gates": ["X1", "X2", "H1", "CNOT"], "shots": 1000 }
    Gate strings mirror the method names on the client-side TwoQubit
    class (static/js/twoqubit.js): X1/X2 flip qubit 1/2, H1 is
    Hadamard on qubit 1, CNOT is controlled-X with qubit 1 as control
    and qubit 2 as target — qc.cx(0, 1) in Qiskit's own qubit numbering
    (qubit 0 here is "qubit 1" in the lesson's 1-indexed naming).
    """
    if not QISKIT_AVAILABLE:
        return (
            jsonify(
                {
                    "error": "qiskit_not_installed",
                    "message": (
                        "qiskit and qiskit-aer aren't installed on this server. "
                        "Run `pip install -r requirements.txt` (they're in there "
                        "now) and restart the app to enable this comparison."
                    ),
                }
            ),
            501,
        )

    data = request.get_json(silent=True) or {}
    gates = data.get("gates", [])
    if not isinstance(gates, list):
        return jsonify({"error": "bad_request", "message": "`gates` must be a list."}), 400

    shots = data.get("shots", 1000)
    try:
        shots = int(shots)
    except (TypeError, ValueError):
        shots = 1000
    shots = max(1, min(shots, 20000))

    qc = QuantumCircuit(2, 2)
    applied = []
    for gate in gates[:100]:
        if not isinstance(gate, str):
            continue
        if gate == "X1":
            qc.x(0)
            applied.append("X1")
        elif gate == "X2":
            qc.x(1)
            applied.append("X2")
        elif gate == "H1":
            qc.h(0)
            applied.append("H1")
        elif gate == "CNOT":
            qc.cx(0, 1)
            applied.append("CNOT")
    qc.measure([0, 1], [0, 1])

    result = AerSimulator().run(qc, shots=shots).result()
    counts = result.get_counts()
    # Qiskit's count-string keys are little-endian (rightmost character
    # is qubit 0, i.e. the lesson's "qubit 1"; second-from-right is
    # qubit 1, i.e. the lesson's "qubit 2") — reorder to the same
    # left-to-right "q1 q2" convention twoqubit.js and the lesson pages
    # use, so the frontend doesn't need to know about this difference.
    out = {"00": 0, "01": 0, "10": 0, "11": 0}
    for bitstring, n in counts.items():
        lesson_q1 = bitstring[-1]
        lesson_q2 = bitstring[-2]
        key = lesson_q1 + lesson_q2
        out[key] = out.get(key, 0) + int(n)

    return jsonify(
        {
            "counts": out,
            "shots": shots,
            "gates_applied": applied,
            "backend": "qiskit-aer AerSimulator",
        }
    )


# ======================================================================
# Restricted code execution (Python IDE's real code editor)
# ======================================================================
# A genuine "write your own Qiskit code and run it" feature — not a
# demo of one. Running arbitrary user-submitted Python server-side is a
# real security problem (filesystem/network/process access, resource
# exhaustion), so this deliberately ISN'T Python's exec() on a raw
# string. Instead: parse the submission with Python's own `ast` module,
# walk the tree, and reject anything that isn't in an explicit
# allowlist — QuantumCircuit construction, a fixed set of gate/measure
# method calls, simple variable assignment, and basic arithmetic. No
# imports, no function/class definitions, no loops or comprehensions,
# no attribute access beyond the allowed method names, no dunder access
# anywhere. That last point matters even for otherwise-"safe" node
# types: `x.__class__.__bases__` is built entirely out of Attribute/
# Name nodes with no dangerous call at all, which is why dunder names
# are rejected on sight rather than only checking Call targets.
#
# Two consequences of not allowing loops: circuits have to be written
# out gate-by-gate (matches how every other example on this page reads
# anyway), and it closes off the most common way "safe-looking" code
# hangs a server (an infinite/near-infinite loop) without needing a
# clever static analysis to prove termination — there's structurally
# no way to loop at all. A signal-based wall-clock timeout is still in
# place as defense in depth, in case this allowlist has a gap I haven't
# found; it's a no-op on Windows (SIGALRM doesn't exist there), which
# only matters if you're running app.py's dev server on Windows —
# gunicorn/Docker deploys are Linux.

_ALLOWED_CODE_NODE_TYPES = (
    ast.Module, ast.Expr, ast.Assign, ast.Call, ast.Attribute, ast.Name,
    ast.Load, ast.Store, ast.Constant, ast.keyword, ast.List, ast.Tuple,
    ast.UnaryOp, ast.USub, ast.UAdd, ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div,
)
_ALLOWED_QC_METHODS = {"h", "x", "y", "z", "ry", "rx", "rz", "cx", "measure", "measure_all", "barrier"}
_MAX_CODE_CHARS = 4000
_MAX_QUBITS = 3
_MAX_GATES = 60


class _CodeValidationError(ValueError):
    pass


def _validate_circuit_code(code):
    """Raises _CodeValidationError with a human-readable message on any
    disallowed construct; returns a compiled code object on success."""
    if not isinstance(code, str) or not code.strip():
        raise _CodeValidationError("No code submitted.")
    if len(code) > _MAX_CODE_CHARS:
        raise _CodeValidationError(f"Code is too long (max {_MAX_CODE_CHARS} characters).")

    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as e:
        raise _CodeValidationError(f"Syntax error: {e.msg} (line {e.lineno}).")

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_CODE_NODE_TYPES):
            raise _CodeValidationError(
                f"'{type(node).__name__}' isn't allowed here — only QuantumCircuit construction, "
                f"gate/measure calls ({', '.join(sorted(_ALLOWED_QC_METHODS))}), and simple "
                f"variable assignment. No imports, loops, or function definitions."
            )
        if isinstance(node, (ast.Name, ast.Attribute)):
            dunder_name = getattr(node, "id", None) or getattr(node, "attr", None)
            if dunder_name and dunder_name.startswith("__"):
                raise _CodeValidationError("Names starting with '__' aren't allowed.")
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                if func.id != "QuantumCircuit":
                    raise _CodeValidationError(
                        f"Only QuantumCircuit(...) can be called directly by name — not {func.id}(...)."
                    )
            elif isinstance(func, ast.Attribute):
                if func.attr not in _ALLOWED_QC_METHODS:
                    raise _CodeValidationError(
                        f"'.{func.attr}(...)' isn't an allowed method — allowed: {', '.join(sorted(_ALLOWED_QC_METHODS))}."
                    )
            else:
                raise _CodeValidationError("Unsupported call expression.")
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if not isinstance(target, ast.Name):
                    raise _CodeValidationError(
                        "Only simple variable assignment (e.g. `qc = ...`) is allowed — "
                        "no attribute, subscript, or tuple-unpacking assignment."
                    )

    return compile(tree, "<user_circuit>", "exec")


@app.route("/api/run-code", methods=["POST"])
def api_run_code():
    """Runs a validated, restricted Python/Qiskit submission and returns
    real measurement counts. Open to everyone, like the other Qiskit
    endpoints — not account data, and the restricted grammar means
    there's nothing here for an anonymous caller to abuse beyond what
    /api/compare-shots already exposes (running a small circuit)."""
    if not QISKIT_AVAILABLE:
        return (
            jsonify(
                {
                    "error": "qiskit_not_installed",
                    "message": "qiskit and qiskit-aer aren't installed on this server. "
                    "Run `pip install -r requirements.txt` and restart the app.",
                }
            ),
            501,
        )

    data = request.get_json(silent=True) or {}
    code = data.get("code", "")
    shots = data.get("shots", 1000)
    try:
        shots = int(shots)
    except (TypeError, ValueError):
        shots = 1000
    shots = max(1, min(shots, 20000))

    try:
        compiled = _validate_circuit_code(code)
    except _CodeValidationError as e:
        return jsonify({"error": "invalid_code", "message": str(e)}), 400

    safe_globals = {"__builtins__": {}, "QuantumCircuit": QuantumCircuit, "pi": math.pi}
    safe_locals = {}

    def _run():
        exec(compiled, safe_globals, safe_locals)

    try:
        if hasattr(signal, "SIGALRM"):
            def _on_timeout(signum, frame):
                raise TimeoutError("Code took too long to run (3s limit).")

            old_handler = signal.signal(signal.SIGALRM, _on_timeout)
            signal.alarm(3)
            try:
                _run()
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        else:
            _run()  # no SIGALRM (e.g. Windows dev) — grammar has no loops, so this still can't hang
    except TimeoutError as e:
        return jsonify({"error": "timeout", "message": str(e)}), 400
    except Exception as e:
        return jsonify({"error": "runtime_error", "message": f"{type(e).__name__}: {e}"}), 400

    qc = safe_locals.get("qc")
    if not isinstance(qc, QuantumCircuit):
        return (
            jsonify({"error": "no_circuit", "message": "Your code needs to assign a QuantumCircuit to a variable named `qc`."}),
            400,
        )
    if qc.num_qubits > _MAX_QUBITS:
        return jsonify({"error": "too_many_qubits", "message": f"Max {_MAX_QUBITS} qubits in this playground."}), 400
    if len(qc.data) > _MAX_GATES:
        return jsonify({"error": "too_many_gates", "message": f"Max {_MAX_GATES} operations."}), 400
    has_measurement = any(instr.operation.name == "measure" for instr in qc.data)
    if not has_measurement:
        return (
            jsonify({"error": "no_measurement", "message": "Add qc.measure_all() or qc.measure(...) so there's something to read out."}),
            400,
        )

    result = AerSimulator().run(qc, shots=shots).result()
    counts = result.get_counts()
    return jsonify(
        {
            "counts": {str(k): int(v) for k, v in counts.items()},
            "shots": shots,
            "num_qubits": qc.num_qubits,
            "backend": "qiskit-aer AerSimulator",
        }
    )


VALID_LESSON_IDS = {"qm-basics", "single-qubit", "two-qubit", "physical-qubit", "hardware-lab", "reality-check"}


def _is_valid_lesson_id(lesson_id):
    """True for the 6 built-in lessons, or for `custom-<slug>` where
    <slug> is a currently-published community lesson (futureplans.md
    #11 — step-checkbox tracking on custom lessons). Unpublishing a
    lesson after someone started it leaves their progress row in the
    DB (harmless, just orphaned) but blocks new writes, since the
    lesson isn't valid to track anymore until republished."""
    if lesson_id in VALID_LESSON_IDS:
        return True
    if lesson_id.startswith("custom-"):
        lesson = db.get_custom_lesson(lesson_id[len("custom-"):])
        return lesson is not None and bool(lesson["published"])
    return False


@app.route("/api/progress")
@login_required
def api_progress_all():
    """{ lesson_id: { done: [...], last_visited } } for the signed-in
    user, across every lesson they've touched. Powers Dashboard's
    "continue" list, the Lessons catalog's progress bars, and Account's
    per-lesson list — one fetch instead of one call per lesson."""
    return jsonify(db.get_all_progress(int(current_user.id)))


@app.route("/api/progress/<lesson_id>/step", methods=["POST"])
@login_required
@csrf_protect
def api_progress_step(lesson_id):
    if not _is_valid_lesson_id(lesson_id):
        return jsonify({"error": "unknown_lesson"}), 404
    data = request.get_json(silent=True) or {}
    step_id = data.get("step_id")
    if not step_id or not isinstance(step_id, str):
        return jsonify({"error": "bad_request", "message": "step_id (string) required"}), 400
    done_list = db.set_step(int(current_user.id), lesson_id, step_id, bool(data.get("done")))
    return jsonify({"done": done_list})


@app.route("/api/progress/<lesson_id>/visit", methods=["POST"])
@login_required
@csrf_protect
def api_progress_visit(lesson_id):
    if not _is_valid_lesson_id(lesson_id):
        return jsonify({"error": "unknown_lesson"}), 404
    ts = db.record_visit(int(current_user.id), lesson_id)
    return jsonify({"last_visited": ts})


if __name__ == "__main__":
    # debug=True auto-reloads on file changes — turn it off before deploying.
    app.run(debug=True, host="0.0.0.0", port=5000)
