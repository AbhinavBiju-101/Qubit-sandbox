"""
Qubit Sandbox — Flask app

Run it with:
    python app.py

Then open http://localhost:5000 in a browser.

Accounts are real: Google OAuth via Authlib + server-side sessions via
Flask-Login, backed by Postgres via Supabase (db.py) for users and
per-account lesson progress. `@login_required` is enforced
server-side — Two Qubits, Physical Qubit, Hardware Lab, Reality Check,
and Account actually redirect anonymous visitors to /login, rather
than just hiding content in the browser.

Google OAuth needs real credentials to work (GOOGLE_CLIENT_ID /
GOOGLE_CLIENT_SECRET env vars — see .env.example and README.md for how
to get them from Google Cloud Console). Without them, GOOGLE_OAUTH_
CONFIGURED is False and /login shows Google sign-in as unavailable
until those are set.

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
import sys
import threading
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
    from qiskit import QuantumCircuit, qasm2
    from qiskit_aer import AerSimulator

    QISKIT_AVAILABLE = True
except ImportError:
    QISKIT_AVAILABLE = False

# Markdown in lesson step bodies (Lesson Creator v2) — optional/lazy
# like qiskit above, so the app still boots without it (steps just
# render as the old plain-text/white-space:pre-line fallback — see
# _render_markdown()). bleach sanitizes the HTML markdown produces
# down to a small allowlist before it's stored, so what's in the DB is
# already safe and custom-lesson.html can render it with `| safe`.
try:
    import bleach
    import markdown as _markdown_lib
    from markdown.extensions import Extension as _MdExtension
    from markdown.treeprocessors import Treeprocessor as _MdTreeprocessor
    import xml.etree.ElementTree as _etree

    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False

_MD_ALLOWED_TAGS = [
    "p", "br", "strong", "em", "b", "i", "u", "s", "del", "mark", "code", "pre", "blockquote",
    "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6", "a", "hr", "table", "thead",
    "tbody", "tr", "th", "td", "span", "div", "details", "summary", "img", "input",
]
_MD_ALLOWED_ATTRS = {
    "a": ["href", "title", "rel"],
    "span": ["class"],
    "code": ["class"],
    "div": ["class"],
    "li": ["class"],
    "ul": ["class"],
    "img": ["src", "alt", "title", "width", "height"],
    "input": ["type", "checked", "disabled"],
    "details": ["class", "open"],
    "summary": [],
}

_CALLOUT_TYPES = {
    "note": {"emoji": "📝", "label": "Note"}, "tip": {"emoji": "💡", "label": "Tip"},
    "important": {"emoji": "❗", "label": "Important"}, "warning": {"emoji": "⚠️", "label": "Warning"},
    "caution": {"emoji": "⚠️", "label": "Caution"}, "danger": {"emoji": "🔥", "label": "Danger"},
    "info": {"emoji": "ℹ️", "label": "Info"}, "question": {"emoji": "❓", "label": "Question"},
    "faq": {"emoji": "❓", "label": "FAQ"}, "success": {"emoji": "✅", "label": "Success"},
    "example": {"emoji": "📋", "label": "Example"}, "quote": {"emoji": "❝", "label": "Quote"},
    "bug": {"emoji": "🐞", "label": "Bug"}, "todo": {"emoji": "☑️", "label": "Todo"},
    "abstract": {"emoji": "📄", "label": "Summary"}, "summary": {"emoji": "📄", "label": "Summary"},
}

if MARKDOWN_AVAILABLE:
    import re as _re
    from markdown.preprocessors import Preprocessor as _MdPreprocessor

    _CALLOUT_RE = _re.compile(r"^\[!(?P<type>[A-Za-z]+)\](?P<fold>[-+]?)\s*(?P<title>.*)$")

    class _ObsidianCalloutTreeprocessor(_MdTreeprocessor):
        """Turns Obsidian-style `> [!NOTE] Title` blockquotes into a
        styled callout (a foldable <details> when a +/- fold marker is
        present, a plain <div> otherwise). Runs AFTER normal blockquote
        parsing, so the first line's plain text is inspected for the
        `[!TYPE]` marker rather than trying to pattern-match raw
        markdown — simpler and correctly handles the rest of the
        blockquote's content having its own inline formatting."""

        def run(self, root):
            for bq in root.iter("blockquote"):
                first = bq.find("p")
                if first is None or not (first.text or "").strip():
                    continue
                # nl2br (in _MD_EXTENSIONS) already turned any "\nmore
                # text" into a <br> child + tail by this point, so
                # first.text IS just the marker line on its own —
                # there's no literal "\n" left to partition on. The
                # rest of the callout body (if any) lives as the tail
                # of that first <br> child, which we splice back in as
                # the new first.text below rather than dropping it.
                m = _CALLOUT_RE.match((first.text or "").strip())
                if not m:
                    continue
                ctype = m.group("type").lower()
                meta = _CALLOUT_TYPES.get(ctype, {"emoji": "📌", "label": m.group("type").capitalize()})
                title = m.group("title").strip() or meta["label"]
                fold = m.group("fold")

                children = list(first)
                if children and children[0].tag == "br":
                    br = children[0]
                    first.text = (br.tail or "").lstrip("\n")
                    first.remove(br)
                else:
                    bq.remove(first)

                title_el = _etree.Element("summary" if fold else "div")
                title_el.set("class", "callout-title")
                title_el.text = f'{meta["emoji"]} {title}'

                if fold:
                    bq.tag = "details"
                    if fold == "+":
                        bq.set("open", "open")
                else:
                    bq.tag = "div"
                bq.set("class", f"callout callout-{ctype}")
                bq.insert(0, title_el)
            return root

    _LIST_ITEM_RE = _re.compile(r"^\s*([-*+]|\d+[.)])\s+\S")
    _ATX_NO_SPACE_RE = _re.compile(r"^(#{1,6})([^\s#])")  # e.g. "#epicc" — Obsidian treats this as
    # a #tag, not a heading (a real ATX heading needs a space after the #s); core
    # python-markdown is looser than that, so this gets escaped before block parsing.
    _BLOCKQUOTE_RE = _re.compile(r"^\s*>")

    class _ObsidianLeniencyPreprocessor(_MdPreprocessor):
        """Three line-level fixes so this behaves closer to how Obsidian
        (and most people's mental model of markdown) actually renders,
        rather than strict CommonMark:

        1. `#word` (no space) is left as literal text/a "tag", not
           turned into a heading — only `# word` is a heading.
        2. A list immediately following a plain text line (no blank
           line between) still renders as a list, not swallowed into
           the preceding paragraph as literal "- item 1" text — this
           is how Obsidian's editor behaves; strict CommonMark requires
           a blank line first.
        3. Two `> [!TYPE]` blockquotes separated only by a blank line
           don't get merged into one blockquote — python-markdown's
           blockquote processor otherwise treats "blank line then more
           '>' lines" as a lazy continuation of the SAME blockquote,
           which would merge two different callouts into one."""

        def run(self, lines):
            out = []
            prev_nonblank = ""
            for i, line in enumerate(lines):
                m = _ATX_NO_SPACE_RE.match(line)
                if m and not line.startswith("#!"):  # keep shebang-in-code-fence-ish lines untouched
                    line = "\\" + line

                if _LIST_ITEM_RE.match(line) and prev_nonblank and not _LIST_ITEM_RE.match(prev_nonblank) \
                        and not _BLOCKQUOTE_RE.match(prev_nonblank) and prev_nonblank.strip() != "":
                    out.append("")  # force a blank line so the list isn't absorbed into the paragraph above

                out.append(line)
                if line.strip() != "":
                    prev_nonblank = line

            # Second pass: split blockquotes separated only by blank line(s).
            final = []
            in_quote = False
            pending_blank = 0
            for line in out:
                is_quote = bool(_BLOCKQUOTE_RE.match(line))
                is_blank = line.strip() == ""
                if is_blank and in_quote:
                    pending_blank += 1
                    final.append(line)
                    continue
                if is_quote and pending_blank > 0:
                    final.insert(len(final) - pending_blank, "<!-- -->")
                    pending_blank = 0
                    in_quote = True
                    final.append(line)
                    continue
                if not is_blank:
                    pending_blank = 0
                    in_quote = is_quote
                final.append(line)
            return final

    class _ObsidianCalloutExtension(_MdExtension):
        def extendMarkdown(self, md):
            md.preprocessors.register(_ObsidianLeniencyPreprocessor(md), "obsidian_leniency", 30)
            md.treeprocessors.register(_ObsidianCalloutTreeprocessor(md), "obsidian_callout", 5)

    _MD_EXTENSIONS = [
        "fenced_code", "tables", "sane_lists", "nl2br",
        "pymdownx.tilde", "pymdownx.mark", "pymdownx.tasklist",
        _ObsidianCalloutExtension(),
    ]
    _MD_EXTENSION_CONFIGS = {"pymdownx.tasklist": {"custom_checkbox": False, "clickable_checkbox": False}}


def _render_markdown(text):
    """Creator-authored step body -> sanitized HTML. Falls back to
    returning None (caller then renders the old plain-text/pre-line
    way) if the markdown/bleach packages aren't installed. `text` is
    already trusted to be this shape (validated + length-capped in
    _validate_lesson_payload) but the OUTPUT is still run through
    bleach — never trust that Markdown-the-library's HTML output is
    automatically safe, since raw <script>/<img onerror> etc. written
    directly into markdown source passes straight through it.

    Supports most of Obsidian's flavor: headings h1–h6, fenced code
    blocks (syntax-highlighted client-side by highlight.js — see
    custom-lesson.html), **bold**/*italic*/***both***/_italic_,
    ~~strikethrough~~, ==highlight==, `inline code`, nested bullet/
    numbered lists, links, images, horizontal rules, GFM task lists,
    tables, blockquotes, and Obsidian-style foldable callouts
    (`> [!NOTE]` etc. — see _ObsidianCalloutTreeprocessor above)."""
    if not MARKDOWN_AVAILABLE or not text:
        return None
    html = _markdown_lib.markdown(text, extensions=_MD_EXTENSIONS, extension_configs=_MD_EXTENSION_CONFIGS)
    return bleach.clean(html, tags=_MD_ALLOWED_TAGS, attributes=_MD_ALLOWED_ATTRS, strip=True)


# ======================================================================
# Auth — Google OAuth (Authlib) + server sessions (Flask-Login)
# ======================================================================

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_OAUTH_CONFIGURED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)

# Creator verification. Two allowlists, both comma-separated real
# email addresses in env vars:
#   CREATOR_EMAILS — signing up as 'creator' with a matching, real
#     Google-verified email auto-verifies instantly. Anyone else who
#     picks 'creator' at signup goes to 'pending' and needs an admin
#     to approve them at /admin/creators.
#   ADMIN_EMAILS — can see/approve/reject pending creator requests at
#     /admin/creators. Computed at request time from current_user.email
#     (see User.is_admin below) rather than stored on the user row, so
#     granting/revoking admin access is just an env var + restart, no
#     migration needed.
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
    auto-'verified' if the email matches CREATOR_EMAILS, otherwise
    'pending'."""
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
    {"key": "gallery", "label": "Gallery", "href": "/gallery", "icon": "stack"},
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
    {"id": "qm-basics", "title": "QM Basics", "href": "/qm-basics", "steps": 3, "description": "State vectors, probability amplitudes, and Born's rule — the prerequisite Single Qubit assumes you already have."},
    {"id": "single-qubit", "title": "Single Qubit", "href": "/single-qubit", "steps": 5, "description": "Build a real qubit, apply gates, and run 1,000 measurements to see superposition collapse into statistics."},
    {"id": "two-qubit", "title": "Two Qubits", "href": "/two-qubit", "steps": 3, "description": "Prepare and identify any of the four basis states, then see what entanglement changes about measurement."},
    {"id": "physical-qubit", "title": "Physical Qubit", "href": "/physical-qubit", "steps": 4, "description": "Josephson junction → transmon → resonator → readout, plus a live temperature/decoherence demo."},
    {"id": "hardware-lab", "title": "Hardware Lab", "href": "/hardware-lab", "steps": 3, "description": "A deeper look at transistor structure, the LC oscillator/zero-resistance analogy, and an actual chip-layout diagram."},
    {"id": "reality-check", "title": "Reality Check", "href": "/reality-check", "steps": 4, "description": "Real published qubit counts, a full system architecture, and the actual scaling bottleneck at 100 qubits."},
]

# Module 2 — "Quantum Algorithms". Every lesson reuses either the
# single-qubit engine (quantum.js) or the small N-qubit register
# engine (multiqubit.js) — real amplitude bookkeeping, not canned
# outcomes, same as everything else in this app.
MODULE_2_LESSONS = [
    {"id": "quantum-teleportation", "title": "Quantum Teleportation", "href": "/quantum-teleportation", "steps": 4, "icon": "teleport", "description": "Move an unknown qubit's state to Bob using a shared Bell pair and two classical bits — no faster-than-light shortcut required."},
    {"id": "superdense-coding", "title": "Superdense Coding", "href": "/superdense-coding", "steps": 4, "icon": "dense", "description": "Send 2 classical bits using entanglement and a single qubit's physical trip — teleportation's exact mirror image."},
    {"id": "deutsch-jozsa", "title": "Deutsch-Jozsa", "href": "/deutsch-jozsa", "steps": 4, "icon": "oracle", "description": "Draw a hidden oracle and determine constant vs. balanced in exactly one query, then check yourself against the reveal."},
    {"id": "grovers-search", "title": "Grover's Search", "href": "/grovers-search", "steps": 4, "icon": "search", "description": "Amplify one marked item from 25% to 100% probability in a single Grover iteration, on a real 4-item search."},
]

# Module 3 — "The Physics and Math Underneath". Placed after Module 2
# so every lesson here can lean on gate/Bloch/entanglement intuition
# the person already has instead of front-loading formalism. See
# futureplans.md for the module-level rationale.
MODULE_3_LESSONS = [
    {"id": "complex-numbers", "title": "Complex Numbers", "href": "/complex-numbers", "steps": 4, "icon": "complex", "description": "Apply a real phase gate to a live qubit and watch probabilities hold still while the Bloch point spins."},
    {"id": "bra-ket", "title": "Bra-Ket, Demystified", "href": "/bra-ket", "steps": 4, "icon": "braket", "description": "Translate a state you build into ket and bra notation with real numbers, then compute live inner products."},
    {"id": "matrices-as-gates", "title": "Matrices as Gates", "href": "/matrices-as-gates", "steps": 4, "icon": "matrix", "description": "Expand a gate's matrix multiplication by hand, then watch two gates disagree about order on the Bloch sphere."},
    {"id": "measurement-postulate", "title": "Measurement & Stern-Gerlach", "href": "/measurement-postulate", "steps": 4, "icon": "measure", "description": "Build a real Stern-Gerlach simulator, then run the sequential Z→X→Z cascade that resets a 'known' spin."},
    {"id": "schrodinger-equation", "title": "The Schrödinger Equation", "href": "/schrodinger-equation", "steps": 4, "icon": "waveeq", "description": "Watch a Bloch vector precess under free evolution, then drive it with a real Rabi-flopping rotation."},
    {"id": "basis-vectors", "title": "Basis Vectors & Hilbert Space", "href": "/basis-vectors", "steps": 4, "icon": "basis", "description": "Express one built state in two different orthonormal bases and verify orthonormality live."},
    {"id": "tensor-products", "title": "Tensor Products", "href": "/tensor-products", "steps": 4, "icon": "tensor", "description": "Build the 4-dimensional joint state of two qubits, then try — and fail — to factor a Bell state back apart."},
    {"id": "operator-types", "title": "Hermitian, Unitary & Projection Operators", "href": "/operator-types", "steps": 4, "icon": "operator", "description": "Classify six real matrices as Hermitian, Unitary, and/or Projection by computing the properties directly."},
    {"id": "eigenvalues-eigenvectors", "title": "Eigenvalues and Eigenvectors", "href": "/eigenvalues-eigenvectors", "steps": 4, "icon": "eigen", "description": "Check whether a candidate vector is really an eigenvector of Z or X, and read off its eigenvalue."},
    {"id": "commutation-relations", "title": "Commutation Relations", "href": "/commutation-relations", "steps": 4, "icon": "commute", "description": "Watch a state go from certain to 50/50 across a non-commuting measurement, then verify [X,Z] by hand."},
]

# Module 4 — "Where Quantum Comes From": the historical/physical
# origin story (wave-particle duality, blackbody radiation, de
# Broglie) plus the applications (particle in a box, tunneling) that
# explain *why* nature needed quantum mechanics at all — cross-linked
# back to Hardware Lab's Josephson-junction tunneling where relevant.
MODULE_4_LESSONS = [
    {"id": "wave-particle-duality", "title": "Wave-Particle Duality", "href": "/wave-particle-duality", "steps": 4, "icon": "duality", "description": "Fire particles one at a time through a double slit and watch the interference pattern build, dot by dot."},
    {"id": "blackbody-radiation", "title": "Blackbody Radiation", "href": "/blackbody-radiation", "steps": 4, "icon": "blackbody", "description": "Plot Planck's law against the classical Rayleigh-Jeans prediction and watch the peak shift with temperature."},
    {"id": "de-broglie", "title": "The de Broglie Wavelength", "href": "/de-broglie", "steps": 4, "icon": "debroglie", "description": "Compare an electron's and a thrown baseball's wavelength on one log-scale ruler."},
    {"id": "particle-in-a-box", "title": "Particle in a Box", "href": "/particle-in-a-box", "steps": 4, "icon": "box", "description": "Watch quantized standing-wave energy levels appear from nothing but 'the wavefunction must fit.'"},
    {"id": "quantum-tunneling", "title": "Quantum Tunneling", "href": "/quantum-tunneling", "steps": 4, "icon": "tunnel", "description": "Shape a barrier and fire particles at it — some tunnel through, at exactly the rate the math predicts."},
    {"id": "three-dimensional-box", "title": "The 3D Box", "href": "/three-dimensional-box", "steps": 4, "icon": "cube", "description": "Search for real degenerate energy levels in a 3D box, computed live from quantum numbers up to 6."},
]

# Module 5 — "Error Correction & Noise". The bit-flip code lesson
# reuses multiqubit.js at n=5 (3 data + 2 syndrome ancillas) — a real
# non-demolition syndrome measurement, not a scripted animation.
MODULE_5_LESSONS = [
    {"id": "decoherence", "title": "Why Qubits Decohere", "href": "/decoherence", "steps": 4, "icon": "decohere", "description": "Watch a Bloch vector's length actually shrink as a qubit loses coherence over a tunable T2."},
    {"id": "bit-flip-code", "title": "Bit-Flip and Phase-Flip Codes", "href": "/bit-flip-code", "steps": 4, "icon": "shield", "description": "Encode, corrupt, and correct a hidden bit-flip error across 5 real qubits, without ever measuring the secret."},
    {"id": "nisq", "title": "NISQ", "href": "/nisq", "steps": 4, "icon": "chip", "description": "Plot how fast circuit success probability collapses as gate count grows, at a realistic per-gate error rate."},
]

# Module 6 — "Quantum Cryptography".
MODULE_6_LESSONS = [
    {"id": "bb84", "title": "BB84 Key Distribution", "href": "/bb84", "steps": 4, "icon": "key", "description": "Run a 16-qubit BB84 key exchange with an Eve toggle, and watch the error rate reveal eavesdropping."},
    {"id": "shors-algorithm", "title": "Why Factoring Matters", "href": "/shors-algorithm", "steps": 4, "icon": "factor", "description": "Find a hidden period in aˣ mod 15 and watch it hand you the factors, 3 × 5, via ordinary gcd."},
]

# One continuous sequence across every built-in module, in display
# order — powers prev/next nav so it flows Module 1 -> 2 -> 3 -> 4 ->
# 5 -> 6 without per-template changes (mirrors LESSON_ORDER's role
# for Module 1 alone, generalized once more than one module existed).
ALL_BUILTIN_LESSONS = (
    LESSON_ORDER + MODULE_2_LESSONS + MODULE_3_LESSONS + MODULE_4_LESSONS
    + MODULE_5_LESSONS + MODULE_6_LESSONS
)

# Module 1's two embeddable widgets (they aren't lessons — no steps/
# progress — but the person asked for them grouped visually alongside
# Module 1's lessons on /lessons and in the Python IDE / Lesson
# Creator's widget picker).
BUILTIN_WIDGETS = [
    {"id": "coin-flip", "title": "Coin Flip (single qubit)", "href": "/embed/coin-flip"},
    {"id": "two-qubit-widget", "title": "Two Qubit / Bell state", "href": "/embed/two-qubit"},
    {"id": "grovers-search-widget", "title": "Grover's Search", "href": "/embed/grovers-search"},
    {"id": "double-slit-widget", "title": "Double Slit", "href": "/embed/double-slit"},
    {"id": "bb84-widget", "title": "BB84 Key Exchange", "href": "/embed/bb84"},
]


def _lesson_nav(lesson_id):
    """Returns (prev_lesson, next_lesson) dicts (or None at either end
    of the sequence) for the given lesson id, per ALL_BUILTIN_LESSONS
    above (Module 1, then Module 3, then Module 4, in that order)."""
    idx = next((i for i, l in enumerate(ALL_BUILTIN_LESSONS) if l["id"] == lesson_id), None)
    if idx is None:
        return None, None
    prev_l = ALL_BUILTIN_LESSONS[idx - 1] if idx > 0 else None
    next_l = ALL_BUILTIN_LESSONS[idx + 1] if idx < len(ALL_BUILTIN_LESSONS) - 1 else None
    return prev_l, next_l


@app.context_processor
def inject_nav():
    """Makes `nav_items`/`csrf_token` available in every template
    without passing them explicitly in each render_template() call
    below. `current_user` is already injected globally by Flask-Login.

    Admin nav entry: previously /admin/creators worked but had NO link
    to it anywhere in the UI — an admin had to already know the URL.
    That's the "where is that?" bug — fixed by appending an Admin item
    here, only for signed-in accounts where current_user.is_admin is
    true (computed from ADMIN_EMAILS — see the User class above)."""
    items = list(NAV_ITEMS)
    if current_user.is_authenticated and current_user.is_admin:
        items.append({"key": "admin", "label": "Admin", "href": "/admin/creators", "icon": "shield", "badge": (str(len(db.list_pending_creators())) if db.list_pending_creators() else None)})
    return {"nav_items": items, "csrf_token": session.get("csrf_token", "")}


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
    # The full lesson catalog, organized into Modules (Module 1 =
    # the built-in lessons + widgets; any published creator module
    # after that; anything a creator hasn't put in a module yet is
    # still listed under "Other community lessons") rather than one
    # flat list.
    catalog = _module_catalog()
    community_modules = catalog[1:]  # catalog[0] is always the builtin Module 1
    standalone = [l for l in db.list_custom_lessons() if l["module_id"] is None]
    return render_template(
        "lessons.html",
        active_page="lessons",
        community_modules=community_modules,
        standalone_lessons=standalone,
    )


def _module_catalog():
    """Builds the unified Modules catalog: the built-in 'Module 1' (its
    lessons come from LESSON_ORDER + BUILTIN_WIDGETS by convention, not
    a DB join — those aren't DB rows) followed by every published
    creator module that has at least one published lesson in it.
    Shared by /lessons, /dashboard, /account, and /api/modules so all
    four stay in sync from one place."""
    builtin = db.get_builtin_module()
    catalog = [
        {
            "id": None,
            "slug": "module-1",
            "title": builtin["title"] if builtin else "Module 1: Foundations",
            "description": builtin["description"] if builtin else "",
            "kind": "builtin",
            "author": None,
            "published": True,
            "lessons": [
                {"id": l["id"], "title": l["title"], "href": l["href"], "steps": l["steps"], "description": l.get("description", ""), "icon": l.get("icon", ""), "kind": "builtin"}
                for l in LESSON_ORDER
            ],
            "widgets": BUILTIN_WIDGETS,
        },
        {
            "id": None,
            "slug": "module-2",
            "title": "Quantum Algorithms",
            "description": "Teleportation, superdense coding, Deutsch-Jozsa, and Grover's search — the first payoff lessons where quantum provably beats classical.",
            "kind": "builtin",
            "badge": "MODULE 2",
            "author": None,
            "published": True,
            "lessons": [
                {"id": l["id"], "title": l["title"], "href": l["href"], "steps": l["steps"], "description": l.get("description", ""), "icon": l.get("icon", ""), "kind": "builtin"}
                for l in MODULE_2_LESSONS
            ],
            "widgets": [],
        },
        {
            "id": None,
            "slug": "module-3",
            "title": "The Physics and Math Underneath",
            "description": "Complex numbers, bra-ket, matrices by hand, Stern-Gerlach, Schrödinger's equation, basis vectors, tensor products, operator types, eigenvalues, and commutation relations.",
            "kind": "builtin",
            "badge": "MODULE 3",
            "author": None,
            "published": True,
            "lessons": [
                {"id": l["id"], "title": l["title"], "href": l["href"], "steps": l["steps"], "description": l.get("description", ""), "icon": l.get("icon", ""), "kind": "builtin"}
                for l in MODULE_3_LESSONS
            ],
            "widgets": [],
        },
        {
            "id": None,
            "slug": "module-4",
            "title": "Where Quantum Comes From",
            "description": "Wave-particle duality, blackbody radiation, de Broglie's wavelength, particle in a box (1D and 3D, with real degeneracy), and tunneling.",
            "kind": "builtin",
            "badge": "MODULE 4",
            "author": None,
            "published": True,
            "lessons": [
                {"id": l["id"], "title": l["title"], "href": l["href"], "steps": l["steps"], "description": l.get("description", ""), "icon": l.get("icon", ""), "kind": "builtin"}
                for l in MODULE_4_LESSONS
            ],
            "widgets": [],
        },
        {
            "id": None,
            "slug": "module-5",
            "title": "Error Correction & Noise",
            "description": "Why qubits decohere, the 3-qubit bit-flip/phase-flip code with real syndrome measurement, and what NISQ means for circuit depth.",
            "kind": "builtin",
            "badge": "MODULE 5",
            "author": None,
            "published": True,
            "lessons": [
                {"id": l["id"], "title": l["title"], "href": l["href"], "steps": l["steps"], "description": l.get("description", ""), "icon": l.get("icon", ""), "kind": "builtin"}
                for l in MODULE_5_LESSONS
            ],
            "widgets": [],
        },
        {
            "id": None,
            "slug": "module-6",
            "title": "Quantum Cryptography",
            "description": "BB84 key distribution with an Eve toggle, and why Shor's algorithm makes factoring-based cryptography quantum-vulnerable.",
            "kind": "builtin",
            "badge": "MODULE 6",
            "author": None,
            "published": True,
            "lessons": [
                {"id": l["id"], "title": l["title"], "href": l["href"], "steps": l["steps"], "description": l.get("description", ""), "icon": l.get("icon", ""), "kind": "builtin"}
                for l in MODULE_6_LESSONS
            ],
            "widgets": [],
        },
    ]
    for m in db.list_published_community_modules():
        author = db.get_user_by_id(m["author_user_id"])
        lessons_in_module = db.list_custom_lessons_by_module(m["id"], published_only=True)
        catalog.append(
            {
                "id": m["id"],
                "slug": m["slug"],
                "title": m["title"],
                "description": m["description"] or "",
                "kind": "community",
                "author": author["name"] if author else "A Qubit Sandbox creator",
                "published": bool(m["published"]),
                "lessons": [
                    {
                        "id": f"custom-{l['slug']}",
                        "title": l["title"],
                        "href": url_for("custom_lesson", slug=l["slug"]),
                        "steps": len(json.loads(l["steps_json"])),
                        "kind": "community",
                    }
                    for l in lessons_in_module
                ],
                "widgets": [],
            }
        )
    return catalog


@app.route("/api/modules")
def api_modules():
    """Powers the module-grouped /lessons catalog and the per-module
    progress bars on Dashboard/Account — client pairs this with
    /api/progress (lesson_id -> done steps) to compute % per module,
    so this endpoint itself needs no auth and carries no per-user data."""
    return jsonify({"modules": _module_catalog()})


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
    # Open to everyone, no sign-in required — quick standalone widgets
    # with no lesson scaffolding around them.
    return render_template("demos.html", active_page="demos")


@app.route("/demos/coin-flip")
def demo_coin_flip():
    # The coin flip simulator. Open to everyone, not gated.
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


# ----------------------------------------------------------------------
# Curated open (no sign-in) demo + embed pages for select Module 2-6
# widgets. Every Module 2-6 lesson is @login_required, which is
# correct for the full lesson experience but meant every one of those
# 25 genuine widgets was undiscoverable outside the gated flow — no
# equivalent to Module 1's /demos page. Rather than open every lesson
# (defeats the point of gating), a curated trio gets the exact same
# open demo + chrome-less embed treatment as /demos/coin-flip:
# Grover's Search (Module 2), the double-slit (Module 4), and BB84
# (Module 6) — one algorithm, one physics visual, one crypto demo.
# Each page's widget JS is a straight copy of the already-verified
# logic in its full lesson, just without the lesson-step scaffolding.
# ----------------------------------------------------------------------

@app.route("/demos/grovers-search")
def demo_grovers_search():
    return render_template("demo-grovers-search.html", active_page="demos")


@app.route("/embed/grovers-search")
def embed_grovers_search():
    return render_template("embed-grovers-search.html")


@app.route("/demos/double-slit")
def demo_double_slit():
    return render_template("demo-double-slit.html", active_page="demos")


@app.route("/embed/double-slit")
def embed_double_slit():
    return render_template("embed-double-slit.html")


@app.route("/demos/bb84")
def demo_bb84():
    return render_template("demo-bb84.html", active_page="demos")


@app.route("/embed/bb84")
def embed_bb84():
    return render_template("embed-bb84.html")


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


# ======================================================================
# Module 2 — Quantum Algorithms
# ======================================================================

@app.route("/quantum-teleportation")
@login_required
def quantum_teleportation():
    prev_l, next_l = _lesson_nav("quantum-teleportation")
    return render_template("quantum-teleportation.html", active_page="lessons", prev_lesson=prev_l, next_lesson=next_l)


@app.route("/superdense-coding")
@login_required
def superdense_coding():
    prev_l, next_l = _lesson_nav("superdense-coding")
    return render_template("superdense-coding.html", active_page="lessons", prev_lesson=prev_l, next_lesson=next_l)


@app.route("/deutsch-jozsa")
@login_required
def deutsch_jozsa():
    prev_l, next_l = _lesson_nav("deutsch-jozsa")
    return render_template("deutsch-jozsa.html", active_page="lessons", prev_lesson=prev_l, next_lesson=next_l)


@app.route("/grovers-search")
@login_required
def grovers_search():
    prev_l, next_l = _lesson_nav("grovers-search")
    return render_template("grovers-search.html", active_page="lessons", prev_lesson=prev_l, next_lesson=next_l)


# ======================================================================
# Module 3 — The Physics and Math Underneath
# ======================================================================

@app.route("/complex-numbers")
@login_required
def complex_numbers():
    prev_l, next_l = _lesson_nav("complex-numbers")
    return render_template("complex-numbers.html", active_page="lessons", prev_lesson=prev_l, next_lesson=next_l)


@app.route("/bra-ket")
@login_required
def bra_ket():
    prev_l, next_l = _lesson_nav("bra-ket")
    return render_template("bra-ket.html", active_page="lessons", prev_lesson=prev_l, next_lesson=next_l)


@app.route("/matrices-as-gates")
@login_required
def matrices_as_gates():
    prev_l, next_l = _lesson_nav("matrices-as-gates")
    return render_template("matrices-as-gates.html", active_page="lessons", prev_lesson=prev_l, next_lesson=next_l)


@app.route("/measurement-postulate")
@login_required
def measurement_postulate():
    prev_l, next_l = _lesson_nav("measurement-postulate")
    return render_template("measurement-postulate.html", active_page="lessons", prev_lesson=prev_l, next_lesson=next_l)


@app.route("/schrodinger-equation")
@login_required
def schrodinger_equation():
    prev_l, next_l = _lesson_nav("schrodinger-equation")
    return render_template("schrodinger-equation.html", active_page="lessons", prev_lesson=prev_l, next_lesson=next_l)


@app.route("/basis-vectors")
@login_required
def basis_vectors():
    prev_l, next_l = _lesson_nav("basis-vectors")
    return render_template("basis-vectors.html", active_page="lessons", prev_lesson=prev_l, next_lesson=next_l)


@app.route("/tensor-products")
@login_required
def tensor_products():
    prev_l, next_l = _lesson_nav("tensor-products")
    return render_template("tensor-products.html", active_page="lessons", prev_lesson=prev_l, next_lesson=next_l)


@app.route("/operator-types")
@login_required
def operator_types():
    prev_l, next_l = _lesson_nav("operator-types")
    return render_template("operator-types.html", active_page="lessons", prev_lesson=prev_l, next_lesson=next_l)


@app.route("/eigenvalues-eigenvectors")
@login_required
def eigenvalues_eigenvectors():
    prev_l, next_l = _lesson_nav("eigenvalues-eigenvectors")
    return render_template("eigenvalues-eigenvectors.html", active_page="lessons", prev_lesson=prev_l, next_lesson=next_l)


@app.route("/commutation-relations")
@login_required
def commutation_relations():
    prev_l, next_l = _lesson_nav("commutation-relations")
    return render_template("commutation-relations.html", active_page="lessons", prev_lesson=prev_l, next_lesson=next_l)


# ======================================================================
# Module 4 — Where Quantum Comes From
# ======================================================================

@app.route("/wave-particle-duality")
@login_required
def wave_particle_duality():
    prev_l, next_l = _lesson_nav("wave-particle-duality")
    return render_template("wave-particle-duality.html", active_page="lessons", prev_lesson=prev_l, next_lesson=next_l)


@app.route("/blackbody-radiation")
@login_required
def blackbody_radiation():
    prev_l, next_l = _lesson_nav("blackbody-radiation")
    return render_template("blackbody-radiation.html", active_page="lessons", prev_lesson=prev_l, next_lesson=next_l)


@app.route("/de-broglie")
@login_required
def de_broglie():
    prev_l, next_l = _lesson_nav("de-broglie")
    return render_template("de-broglie.html", active_page="lessons", prev_lesson=prev_l, next_lesson=next_l)


@app.route("/particle-in-a-box")
@login_required
def particle_in_a_box():
    prev_l, next_l = _lesson_nav("particle-in-a-box")
    return render_template("particle-in-a-box.html", active_page="lessons", prev_lesson=prev_l, next_lesson=next_l)


@app.route("/quantum-tunneling")
@login_required
def quantum_tunneling():
    prev_l, next_l = _lesson_nav("quantum-tunneling")
    return render_template("quantum-tunneling.html", active_page="lessons", prev_lesson=prev_l, next_lesson=next_l)


@app.route("/three-dimensional-box")
@login_required
def three_dimensional_box():
    prev_l, next_l = _lesson_nav("three-dimensional-box")
    return render_template("three-dimensional-box.html", active_page="lessons", prev_lesson=prev_l, next_lesson=next_l)


# ======================================================================
# Module 5 — Error Correction & Noise
# ======================================================================

@app.route("/decoherence")
@login_required
def decoherence():
    prev_l, next_l = _lesson_nav("decoherence")
    return render_template("decoherence.html", active_page="lessons", prev_lesson=prev_l, next_lesson=next_l)


@app.route("/bit-flip-code")
@login_required
def bit_flip_code():
    prev_l, next_l = _lesson_nav("bit-flip-code")
    return render_template("bit-flip-code.html", active_page="lessons", prev_lesson=prev_l, next_lesson=next_l)


@app.route("/nisq")
@login_required
def nisq():
    prev_l, next_l = _lesson_nav("nisq")
    return render_template("nisq.html", active_page="lessons", prev_lesson=prev_l, next_lesson=next_l)


# ======================================================================
# Module 6 — Quantum Cryptography
# ======================================================================

@app.route("/bb84")
@login_required
def bb84():
    prev_l, next_l = _lesson_nav("bb84")
    return render_template("bb84.html", active_page="lessons", prev_lesson=prev_l, next_lesson=next_l)


@app.route("/shors-algorithm")
@login_required
def shors_algorithm():
    prev_l, next_l = _lesson_nav("shors-algorithm")
    return render_template("shors-algorithm.html", active_page="lessons", prev_lesson=prev_l, next_lesson=next_l)


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
    # the account-type/CREATOR_EMAILS model above). Management of past
    # submissions (edit/delete/publish, modules, widgets) now lives on
    # its own page — see /creator/submissions — this route stays
    # focused on the "write/edit one lesson" form; `?edit=<id>` loads
    # an existing lesson of yours into that form (LESSON_EDIT_DATA
    # below carries the payload client-side, no extra fetch needed).
    my_lessons, my_modules, my_widgets = [], [], []
    edit_lesson = None
    if current_user.is_authenticated and current_user.can_create_lessons:
        my_lessons = db.list_custom_lessons_by_author(int(current_user.id))
        my_modules = db.list_modules_by_author(int(current_user.id))
        my_widgets = db.list_custom_widgets_by_author(int(current_user.id))
        edit_id = request.args.get("edit", type=int)
        if edit_id:
            candidate = db.get_custom_lesson_by_id(edit_id)
            if candidate is not None and candidate["author_user_id"] == int(current_user.id):
                edit_lesson = candidate
    edit_lesson_data = None
    if edit_lesson is not None:
        edit_lesson_data = {
            "id": edit_lesson["id"],
            "title": edit_lesson["title"],
            "description": edit_lesson["description"],
            "steps": json.loads(edit_lesson["steps_json"]),
            "module_id": edit_lesson["module_id"],
        }
    return render_template(
        "lesson-creator.html",
        active_page="creator",
        my_lessons=my_lessons,
        my_modules=my_modules,
        my_widgets=my_widgets,
        edit_lesson_data=edit_lesson_data,
    )


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
MAX_CHECKLIST_ITEMS = 6


def _valid_widget_ref(widget, author_id):
    """None/"coin-flip"/"two-qubit" are always fine; "custom-<id>" is
    only fine if that widget exists AND was authored by this creator
    (a step can't embed someone else's saved widget)."""
    if widget in (None, "coin-flip", "two-qubit"):
        return True
    if isinstance(widget, str) and widget.startswith("custom-"):
        try:
            widget_id = int(widget[len("custom-"):])
        except ValueError:
            return False
        w = db.get_custom_widget_by_id(widget_id)
        return w is not None and w["author_user_id"] == author_id
    return False


def _validate_lesson_payload(data, author_id):
    """Shared by create and edit. Returns (title, description, steps,
    module_id) on success, or (None, None, error_response, None) on
    failure — check `steps is None` to tell which case you got."""
    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    raw_steps = data.get("steps")
    raw_module_id = data.get("module_id")

    if not title or len(title) > 200:
        return None, None, (jsonify({"error": "bad_request", "message": "Title is required (max 200 chars)."}), 400), None
    if not isinstance(raw_steps, list) or not (1 <= len(raw_steps) <= MAX_LESSON_STEPS):
        return None, None, (jsonify({"error": "bad_request", "message": f"Need 1–{MAX_LESSON_STEPS} steps."}), 400), None

    module_id = None
    if raw_module_id not in (None, "", 0, "0"):
        try:
            module_id = int(raw_module_id)
        except (TypeError, ValueError):
            return None, None, (jsonify({"error": "bad_request", "message": "Invalid module."}), 400), None
        m = db.get_module_by_id(module_id)
        if m is None or m["author_user_id"] != author_id:
            return None, None, (jsonify({"error": "bad_request", "message": "Not your module."}), 400), None

    steps = []
    for s in raw_steps:
        if not isinstance(s, dict):
            return None, None, (jsonify({"error": "bad_request", "message": "Each step must be an object."}), 400), None
        step_title = (s.get("title") or "").strip()
        body = (s.get("body") or "").strip()
        widget = s.get("widget") or None
        raw_checklist = s.get("checklist") or []
        if not step_title or len(step_title) > 120:
            return None, None, (jsonify({"error": "bad_request", "message": "Each step needs a title (max 120 chars)."}), 400), None
        if len(body) > 4000:
            return None, None, (jsonify({"error": "bad_request", "message": "Step body is too long (max 4000 chars)."}), 400), None
        if not _valid_widget_ref(widget, author_id):
            return None, None, (jsonify({"error": "bad_request", "message": f"Unknown or not-your widget: {widget!r}"}), 400), None
        if not isinstance(raw_checklist, list) or len(raw_checklist) > MAX_CHECKLIST_ITEMS:
            return None, None, (jsonify({"error": "bad_request", "message": f"Max {MAX_CHECKLIST_ITEMS} custom checklist items per step."}), 400), None
        checklist = []
        for item in raw_checklist:
            item = (item or "").strip() if isinstance(item, str) else ""
            if item:
                if len(item) > 200:
                    return None, None, (jsonify({"error": "bad_request", "message": "Checklist item too long (max 200 chars)."}), 400), None
                checklist.append(item)
        steps.append({"title": step_title, "body": body, "widget": widget, "checklist": checklist})

    return title, description, steps, module_id


@app.route("/api/lessons", methods=["POST"])
@login_required
@csrf_protect
def api_create_lesson():
    """Creates a custom lesson — verified creator accounts only (403
    for everyone else, including regular signed-in students and
    creators still pending approval). `published: false` in the
    payload creates it as a draft (see draft/preview-mode below)
    instead of going live immediately — a preview token is generated
    automatically so the creator has a shareable link right away."""
    if not current_user.can_create_lessons:
        return jsonify({"error": "forbidden", "message": "Verified creator account required."}), 403

    data = request.get_json(silent=True) or {}
    title, description, steps, module_id = _validate_lesson_payload(data, int(current_user.id))
    if title is None:
        return steps  # _validate_lesson_payload stashed the (response, status) error tuple here on failure

    publish_now = data.get("published", True) is not False
    lesson = db.create_custom_lesson(int(current_user.id), title, description, steps, module_id, published=publish_now)
    preview_url = None
    if not publish_now:
        token = secrets.token_urlsafe(16)
        db.set_lesson_preview_token(lesson["id"], token)
        preview_url = url_for("custom_lesson_preview", slug=lesson["slug"], token=token)
    return jsonify({
        "slug": lesson["slug"],
        "url": url_for("custom_lesson", slug=lesson["slug"]),
        "published": publish_now,
        "preview_url": preview_url,
    })


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
    title, description, steps, module_id = _validate_lesson_payload(data, int(current_user.id))
    if title is None:
        return steps

    updated = db.update_custom_lesson(lesson_id, title, description, steps, module_id)
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


@app.route("/api/lessons/<int:lesson_id>/module", methods=["POST"])
@login_required
@csrf_protect
def api_set_lesson_module(lesson_id):
    """Quick reassignment of a lesson's module from the My Submissions
    page, without going through the full edit form."""
    if not current_user.can_create_lessons:
        return jsonify({"error": "forbidden", "message": "Verified creator account required."}), 403
    lesson, err = _get_own_lesson_or_403(lesson_id)
    if lesson is None:
        return err
    data = request.get_json(silent=True) or {}
    raw = data.get("module_id")
    module_id = None
    if raw not in (None, "", 0, "0"):
        try:
            module_id = int(raw)
        except (TypeError, ValueError):
            return jsonify({"error": "bad_request"}), 400
        m = db.get_module_by_id(module_id)
        if m is None or m["author_user_id"] != int(current_user.id):
            return jsonify({"error": "bad_request", "message": "Not your module."}), 400
    db.set_lesson_module(lesson_id, module_id)
    return jsonify({"module_id": module_id})


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


# --------------------------------------------------------------------
# Creator modules — a named, ordered set of a creator's own lessons,
# published together (see `modules` table in db.py).
# --------------------------------------------------------------------

MAX_MODULE_TITLE = 200
MAX_MODULE_DESC = 500


def _get_own_module_or_403(module_id):
    m = db.get_module_by_id(module_id)
    if m is None:
        return None, (jsonify({"error": "not_found"}), 404)
    if m["author_user_id"] != int(current_user.id):
        return None, (jsonify({"error": "forbidden", "message": "Not your module."}), 403)
    return m, None


@app.route("/api/creator-modules", methods=["POST"])
@login_required
@csrf_protect
def api_create_module():
    if not current_user.can_create_lessons:
        return jsonify({"error": "forbidden", "message": "Verified creator account required."}), 403
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    if not title or len(title) > MAX_MODULE_TITLE:
        return jsonify({"error": "bad_request", "message": f"Title is required (max {MAX_MODULE_TITLE} chars)."}), 400
    if len(description) > MAX_MODULE_DESC:
        return jsonify({"error": "bad_request", "message": f"Description too long (max {MAX_MODULE_DESC} chars)."}), 400
    m = db.create_module(int(current_user.id), title, description)
    return jsonify({"id": m["id"], "slug": m["slug"], "title": m["title"]})


@app.route("/api/creator-modules/<int:module_id>", methods=["PUT"])
@login_required
@csrf_protect
def api_edit_module(module_id):
    m, err = _get_own_module_or_403(module_id)
    if m is None:
        return err
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    if not title or len(title) > MAX_MODULE_TITLE:
        return jsonify({"error": "bad_request", "message": f"Title is required (max {MAX_MODULE_TITLE} chars)."}), 400
    updated = db.update_module(module_id, title, description)
    return jsonify({"id": updated["id"], "title": updated["title"]})


@app.route("/api/creator-modules/<int:module_id>/publish", methods=["POST"])
@login_required
@csrf_protect
def api_toggle_publish_module(module_id):
    m, err = _get_own_module_or_403(module_id)
    if m is None:
        return err
    data = request.get_json(silent=True) or {}
    published = bool(data.get("published"))
    db.set_module_published(module_id, published, publish_lessons_too=True)
    return jsonify({"published": published})


@app.route("/api/creator-modules/<int:module_id>", methods=["DELETE"])
@login_required
@csrf_protect
def api_delete_module(module_id):
    m, err = _get_own_module_or_403(module_id)
    if m is None:
        return err
    db.delete_module(module_id)
    return jsonify({"deleted": True})


# --------------------------------------------------------------------
# Creator widgets — a saved restricted-grammar circuit (same AST
# validator as /api/run-code), embeddable in a lesson step. Built from
# the Python IDE ("save as widget") or the Lesson Creator directly.
# --------------------------------------------------------------------

MAX_WIDGET_TITLE = 120


@app.route("/api/widgets", methods=["GET"])
@login_required
def api_list_widgets():
    if not current_user.can_create_lessons:
        return jsonify({"error": "forbidden"}), 403
    widgets = db.list_custom_widgets_by_author(int(current_user.id))
    return jsonify({"widgets": [{"id": w["id"], "title": w["title"], "code": w["code"]} for w in widgets]})


@app.route("/api/widgets", methods=["POST"])
@login_required
@csrf_protect
def api_create_widget():
    if not current_user.can_create_lessons:
        return jsonify({"error": "forbidden", "message": "Verified creator account required."}), 403
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    code = data.get("code") or ""
    if not title or len(title) > MAX_WIDGET_TITLE:
        return jsonify({"error": "bad_request", "message": f"Title is required (max {MAX_WIDGET_TITLE} chars)."}), 400
    try:
        _validate_circuit_code(code)
    except _CodeValidationError as e:
        return jsonify({"error": "invalid_code", "message": str(e)}), 400
    w = db.create_custom_widget(int(current_user.id), title, code)
    return jsonify({"id": w["id"], "title": w["title"], "widget_ref": f"custom-{w['id']}"})


@app.route("/api/widgets/<int:widget_id>")
def api_get_widget(widget_id):
    # Publicly readable (no @login_required): a published lesson step
    # can embed this for any visitor to run, same posture as the
    # lesson content itself. Read-only — running it goes through the
    # existing, separately-validated /api/run-code.
    w = db.get_custom_widget_by_id(widget_id)
    if w is None:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"id": w["id"], "title": w["title"], "code": w["code"]})


@app.route("/api/widgets/<int:widget_id>", methods=["DELETE"])
@login_required
@csrf_protect
def api_delete_widget(widget_id):
    w = db.get_custom_widget_by_id(widget_id)
    if w is None:
        return jsonify({"error": "not_found"}), 404
    if w["author_user_id"] != int(current_user.id):
        return jsonify({"error": "forbidden"}), 403
    db.delete_custom_widget(widget_id)
    return jsonify({"deleted": True})


@app.route("/creator/submissions")
@login_required
def creator_submissions():
    # The dedicated "My Submissions" page: every lesson AND every
    # module this creator has authored, with edit/delete/publish
    # controls — split out from /lesson-creator (which stays focused on
    # the "write something new" form) now that there's enough to manage
    # (modules + widgets alongside lessons) to warrant its own page.
    if not current_user.can_create_lessons:
        abort(403)
    my_lessons = db.list_custom_lessons_by_author(int(current_user.id))
    my_modules = db.list_modules_by_author(int(current_user.id))
    my_widgets = db.list_custom_widgets_by_author(int(current_user.id))
    return render_template(
        "creator-submissions.html",
        active_page="creator",
        my_lessons=my_lessons,
        my_modules=my_modules,
        my_widgets=my_widgets,
    )


# --------------------------------------------------------------------
# Gamification — daily streaks, hours studied, unlockable badges.
# --------------------------------------------------------------------

def _today_str():
    import datetime

    return datetime.datetime.utcnow().strftime("%Y-%m-%d")


def _compute_streaks(dates):
    """`dates` is a sorted list of 'YYYY-MM-DD' strings. Returns
    (current_streak, longest_streak). Current streak counts back from
    today (or yesterday, so a streak isn't lost just because you
    haven't opened the app yet today) as long as consecutive calendar
    days are present."""
    import datetime

    if not dates:
        return 0, 0
    day_set = {datetime.date.fromisoformat(d) for d in dates}
    longest = 1
    run = 1
    sorted_days = sorted(day_set)
    for i in range(1, len(sorted_days)):
        if (sorted_days[i] - sorted_days[i - 1]).days == 1:
            run += 1
        else:
            run = 1
        longest = max(longest, run)

    today = datetime.date.today()
    current = 0
    cursor = today if today in day_set else (today - datetime.timedelta(days=1))
    if cursor in day_set:
        current = 1
        d = cursor
        while (d - datetime.timedelta(days=1)) in day_set:
            d = d - datetime.timedelta(days=1)
            current += 1
    return current, longest


def _lesson_completion_map(user_id):
    """{ lesson_id: bool completed } across built-in + every custom
    lesson this user has ever touched — used for the completion-count
    badges (first-lesson, five-lessons, module-1-done)."""
    progress = db.get_all_progress(user_id)
    completed = {}
    builtin_steps = {l["id"]: l["steps"] for l in LESSON_ORDER}
    for lid, total_steps in builtin_steps.items():
        entry = progress.get(lid) or {"done": []}
        completed[lid] = len(entry.get("done") or []) >= total_steps
    for lid, entry in progress.items():
        if lid in builtin_steps or not lid.startswith("custom-"):
            continue
        lesson = db.get_custom_lesson(lid[len("custom-"):])
        if lesson is None:
            continue
        steps = json.loads(lesson["steps_json"])
        total = sum(1 + len(s.get("checklist") or []) for s in steps)
        completed[lid] = len(entry.get("done") or []) >= max(total, 1)
    return completed


def compute_and_sync_badges(user_id, local_hour=None):
    """Recomputes every badge condition and persists any newly-earned
    ones (db.award_badge_if_new is idempotent). Returns the list of
    badge_keys earned for THE FIRST TIME by this call, so callers (the
    activity ping, step-completion) can surface a "badge unlocked!"
    toast — an empty list means nothing new."""
    newly_earned = []

    def _try(key, condition):
        if condition and db.award_badge_if_new(user_id, key):
            newly_earned.append(key)

    dates = db.get_activity_dates(user_id)
    current_streak, longest_streak = _compute_streaks(dates)
    _try("streak-3", longest_streak >= 3)
    _try("streak-7", longest_streak >= 7)
    _try("streak-30", longest_streak >= 30)

    import datetime

    weekdays = {datetime.date.fromisoformat(d).weekday() for d in dates}  # Mon=0..Sun=6
    _try("weekend-studier", 5 in weekdays and 6 in weekdays)

    total_hours = db.get_total_minutes(user_id) / 60.0
    _try("hours-10", total_hours >= 10)
    _try("hours-40", total_hours >= 40)

    if local_hour is not None:
        _try("early-bird", 0 <= local_hour < 7)
        _try("night-owl", local_hour >= 23)

    completed = _lesson_completion_map(user_id)
    completed_count = sum(1 for v in completed.values() if v)
    _try("first-lesson", completed_count >= 1)
    _try("five-lessons", completed_count >= 5)
    builtin_ids = [l["id"] for l in LESSON_ORDER]
    _try("module-1-done", all(completed.get(lid) for lid in builtin_ids))

    return newly_earned


@app.route("/api/activity/ping", methods=["POST"])
@login_required
@csrf_protect
def api_activity_ping():
    """Called every ~60s by a page that's open and focused (lesson,
    demo, sandbox, Python IDE — see lesson-progress.js) to log one
    minute of activity for today and re-check badges. Coarse on
    purpose — this is a "were you actively here" signal for streaks/
    hours badges, not a billing-grade timer."""
    data = request.get_json(silent=True) or {}
    local_hour = data.get("local_hour")
    try:
        local_hour = int(local_hour) if local_hour is not None else None
    except (TypeError, ValueError):
        local_hour = None
    db.record_activity(int(current_user.id), _today_str(), minutes=1)
    newly_earned = compute_and_sync_badges(int(current_user.id), local_hour=local_hour)
    return jsonify({"ok": True, "newly_earned": newly_earned})


@app.route("/api/gamification")
@login_required
def api_gamification():
    """Streak/hours/badges summary for Dashboard + Account."""
    user_id = int(current_user.id)
    dates = db.get_activity_dates(user_id)
    current_streak, longest_streak = _compute_streaks(dates)
    total_minutes = db.get_total_minutes(user_id)
    earned = db.get_user_badges(user_id)
    badges = [
        {"key": k, **meta, "earned_at": earned.get(k)}
        for k, meta in db.BADGE_CATALOG.items()
    ]
    badges.sort(key=lambda b: (b["earned_at"] is None, -(b["earned_at"] or 0)))
    return jsonify(
        {
            "current_streak": current_streak,
            "longest_streak": longest_streak,
            "total_minutes": total_minutes,
            "total_hours": round(total_minutes / 60.0, 1),
            "days_active": len(dates),
            "badges": badges,
            "earned_count": len(earned),
            "total_count": len(db.BADGE_CATALOG),
        }
    )


@app.route("/lessons/custom/<slug>")
def custom_lesson(slug):
    # Published custom lessons are open to everyone, same as the
    # built-in open lessons — no reason to gate community content
    # behind sign-in when QM Basics/Single Qubit aren't either. An
    # unpublished lesson is visible only to its own author (so they can
    # preview/edit it — see api_toggle_publish_lesson) or via a
    # preview-token link (see custom_lesson_preview), 404 for anyone
    # else, same as a nonexistent slug (doesn't leak that it exists).
    lesson = db.get_custom_lesson(slug)
    if lesson is None:
        abort(404)
    is_own = current_user.is_authenticated and lesson["author_user_id"] == int(current_user.id)
    if not lesson["published"] and not is_own:
        abort(404)
    return _render_custom_lesson(lesson, is_own=is_own)


def _render_custom_lesson(lesson, is_own=False, is_preview=False):
    """Shared by the normal /lessons/custom/<slug> route and the
    preview-token route (custom_lesson_preview) — same rendering,
    different access-check logic in the two callers."""
    steps = json.loads(lesson["steps_json"])
    # Markdown → sanitized HTML per step (falls back to None, meaning
    # "render the old plain-text/pre-line way", if Markdown/bleach
    # aren't installed — see _render_markdown()).
    for step in steps:
        step["body_html"] = _render_markdown(step.get("body", ""))
        step.setdefault("checklist", [])
    author = db.get_user_by_id(lesson["author_user_id"])
    can_fork = (
        current_user.is_authenticated
        and current_user.can_create_lessons
        and lesson["author_user_id"] != int(current_user.id)
        and bool(lesson["published"])
    )
    return render_template(
        "custom-lesson.html",
        active_page="lessons",
        lesson=lesson,
        steps=steps,
        is_own=is_own,
        is_preview=is_preview,
        can_fork=can_fork,
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


@app.route("/python-ide/editor")
def python_ide_editor():
    # The real, dedicated full-page IDE (fixes the "Open in editor just
    # scrolls to a tiny textarea" complaint) — its own page with a
    # proper code area, a console/output panel that keeps a run
    # history instead of overwriting the last result, and a collapsible
    # gate-reference sidebar. Every "Open in editor" button on
    # /python-ide hands code off here via sessionStorage (see that
    # page's openInEditor()) rather than embedding this UI inline.
    # "Save as widget" only actually works for verified creators
    # (current_user.can_create_lessons) — shown to everyone but the
    # button explains itself if you're not one yet.
    return render_template("python-ide-editor.html", active_page="ide")


@app.route("/login")
def login():
    if current_user.is_authenticated:
        return redirect(_safe_next(request.args.get("next")) or url_for("dashboard"))
    return render_template("login.html", google_oauth_configured=GOOGLE_OAUTH_CONFIGURED)


@app.route("/signup")
def signup():
    # Distinct from /login: this is where a NEW visitor picks an
    # account type (student/educator/creator) before authenticating.
    # The actual auth is identical to /login's — signup.html's Google
    # button just adds ?type=<picked> to /auth/google/login, which only
    # applies it if the resulting account is freshly created (see
    # google_callback above). Returning users who land here by mistake
    # just get signed in normally, their existing type kept.
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
# method calls, a small set of safe builtins (range/print/input/len/
# abs/min/max/int/float/str/bool/enumerate), variable assignment,
# basic arithmetic/comparison/boolean logic, and for/while loops with
# if/elif/else branching. No imports, no function/class definitions,
# no comprehensions, no attribute access beyond the allowed method
# names, no dunder access anywhere. That last point matters even for
# otherwise-"safe" node types: `x.__class__.__bases__` is built
# entirely out of Attribute/Name nodes with no dangerous call at all,
# which is why dunder names are rejected on sight rather than only
# checking Call targets.
#
# Loops mean the AST allowlist alone can no longer bound how many gates
# get applied (a `for` loop can call qc.h(0) a million times) — so
# _run_validated_circuit below also wraps every allowed QuantumCircuit
# method with a live counter that aborts mid-loop once _MAX_GATES is
# exceeded, rather than only checking len(qc.data) after the fact. That
# wrap wrap is done on the QuantumCircuit class itself (process-global),
# so _RUN_CODE_LOCK serializes concurrent /api/run-code calls — an
# acceptable trade-off for a small educational sandbox, not a
# high-throughput API. A signal-based wall-clock timeout is still in
# place as defense in depth against a loop that spins CPU without ever
# calling a qc method (e.g. `while True: x = x + 1`); it's a no-op on
# Windows (SIGALRM doesn't exist there), which only matters if you're
# running app.py's dev server on Windows — gunicorn/Docker deploys are
# Linux.

_ALLOWED_CODE_NODE_TYPES = (
    ast.Module, ast.Expr, ast.Assign, ast.AugAssign, ast.Call, ast.Attribute, ast.Name,
    ast.Load, ast.Store, ast.Constant, ast.keyword, ast.List, ast.Tuple, ast.Subscript, ast.Slice,
    ast.UnaryOp, ast.USub, ast.UAdd, ast.Not, ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div,
    ast.FloorDiv, ast.Mod, ast.Pow,
    ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot,
    ast.BoolOp, ast.And, ast.Or,
    ast.If, ast.For, ast.While, ast.Break, ast.Continue, ast.Pass,
    ast.JoinedStr, ast.FormattedValue,
)
_ALLOWED_QC_METHODS = {"h", "x", "y", "z", "ry", "rx", "rz", "cx", "measure", "measure_all", "barrier"}
_ALLOWED_BARE_CALLS = {"QuantumCircuit", "range", "print", "input", "len", "abs", "min", "max", "int", "float", "str", "bool", "enumerate"}
_MAX_CODE_CHARS = 4000
_MAX_QUBITS = 3
_MAX_GATES = 60
_MAX_LOOP_STEPS = 200_000  # bounds `for`/`while` bodies unrelated to qc calls (e.g. plain counting)

_RUN_CODE_LOCK = threading.Lock()


class _CodeValidationError(ValueError):
    pass


class _TooManyOperationsError(RuntimeError):
    pass


class _TooManyStepsError(RuntimeError):
    pass


class _OutOfInputError(RuntimeError):
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
                f"'{type(node).__name__}' isn't allowed here — allowed: QuantumCircuit construction, "
                f"gate/measure calls ({', '.join(sorted(_ALLOWED_QC_METHODS))}), assignment, arithmetic, "
                f"comparisons, if/elif/else, for/while loops, and {', '.join(sorted(_ALLOWED_BARE_CALLS))}. "
                f"Still no imports or function/class definitions."
            )
        if isinstance(node, (ast.Name, ast.Attribute)):
            dunder_name = getattr(node, "id", None) or getattr(node, "attr", None)
            if dunder_name and dunder_name.startswith("__"):
                raise _CodeValidationError("Names starting with '__' aren't allowed.")
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                if func.id not in _ALLOWED_BARE_CALLS:
                    raise _CodeValidationError(
                        f"'{func.id}(...)' isn't allowed — allowed by name: {', '.join(sorted(_ALLOWED_BARE_CALLS))}."
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
                if not isinstance(target, (ast.Name, ast.Subscript)):
                    raise _CodeValidationError(
                        "Only simple variable assignment (e.g. `qc = ...` or `x[0] = ...`) is allowed — "
                        "no attribute or tuple-unpacking assignment."
                    )
        if isinstance(node, ast.For):
            if not isinstance(node.target, ast.Name):
                raise _CodeValidationError("Only a single loop variable is allowed in `for x in ...:` — no tuple unpacking.")

    return compile(tree, "<user_circuit>", "exec")


def _run_validated_circuit(compiled, safe_globals, safe_locals):
    """Executes already-validated code with two live guards a static
    AST pass can't provide once loops are allowed: a hard cap on total
    QuantumCircuit operations (wrapping the class — see _RUN_CODE_LOCK
    note above) and a hard cap on total loop-body iterations (via
    sys.settrace, so a loop that never touches `qc` still can't spin
    past _MAX_LOOP_STEPS before the SIGALRM timeout would catch it)."""
    op_counter = {"n": 0}
    step_counter = {"n": 0}
    originals = {}

    def _make_wrapper(name, orig_fn):
        def wrapper(self, *a, **kw):
            op_counter["n"] += 1
            if op_counter["n"] > _MAX_GATES:
                raise _TooManyOperationsError(f"Too many circuit operations (max {_MAX_GATES}).")
            return orig_fn(self, *a, **kw)
        return wrapper

    def _tracer(frame, event, arg):
        if event == "line":
            step_counter["n"] += 1
            if step_counter["n"] > _MAX_LOOP_STEPS:
                raise _TooManyStepsError(f"Too many steps executed (max {_MAX_LOOP_STEPS}) — check for an infinite loop.")
        return _tracer

    for name in _ALLOWED_QC_METHODS:
        originals[name] = getattr(QuantumCircuit, name)
        setattr(QuantumCircuit, name, _make_wrapper(name, originals[name]))
    try:
        sys.settrace(_tracer)
        exec(compiled, safe_globals, safe_locals)
    finally:
        sys.settrace(None)
        for name, orig in originals.items():
            setattr(QuantumCircuit, name, orig)


def _make_sandboxed_input(stdin_lines):
    """A batch-judge-style input(): pops the next pre-supplied line
    instead of reading real stdin (there isn't any — this runs inside a
    Flask request, non-interactively). The client can optionally send
    a `stdin` string (newline-separated) in the request body; each
    input() call consumes the next line."""
    lines = list(stdin_lines)

    def _input(prompt=""):
        if not lines:
            raise _OutOfInputError(
                "input() was called but there's no more input provided — add it in the \"stdin\" box."
            )
        return lines.pop(0)

    return _input


def _make_sandboxed_print(buffer, max_chars=4000):
    def _print(*args, sep=" ", end="\n"):
        if len(buffer["text"]) >= max_chars:
            return
        buffer["text"] += sep.join(str(a) for a in args) + end
        if len(buffer["text"]) > max_chars:
            buffer["text"] = buffer["text"][:max_chars] + "\n… (output truncated)"
    return _print


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
    stdin_text = data.get("stdin", "") or ""
    stdin_lines = stdin_text.split("\n") if stdin_text else []

    try:
        compiled = _validate_circuit_code(code)
    except _CodeValidationError as e:
        return jsonify({"error": "invalid_code", "message": str(e)}), 400

    print_buffer = {"text": ""}
    safe_builtins = {
        "range": range, "len": len, "abs": abs, "min": min, "max": max,
        "int": int, "float": float, "str": str, "bool": bool, "enumerate": enumerate,
        "print": _make_sandboxed_print(print_buffer),
        "input": _make_sandboxed_input(stdin_lines),
    }
    safe_globals = {"__builtins__": safe_builtins, "QuantumCircuit": QuantumCircuit, "pi": math.pi}
    safe_locals = {}

    with _RUN_CODE_LOCK:
        try:
            if hasattr(signal, "SIGALRM"):
                def _on_timeout(signum, frame):
                    raise TimeoutError("Code took too long to run (3s limit) — check for a runaway loop.")

                old_handler = signal.signal(signal.SIGALRM, _on_timeout)
                signal.alarm(3)
                try:
                    _run_validated_circuit(compiled, safe_globals, safe_locals)
                finally:
                    signal.alarm(0)
                    signal.signal(signal.SIGALRM, old_handler)
            else:
                _run_validated_circuit(compiled, safe_globals, safe_locals)  # no SIGALRM (e.g. Windows dev)
        except TimeoutError as e:
            return jsonify({"error": "timeout", "message": str(e), "console": print_buffer["text"]}), 400
        except (_TooManyOperationsError, _TooManyStepsError, _OutOfInputError) as e:
            return jsonify({"error": "runtime_error", "message": str(e), "console": print_buffer["text"]}), 400
        except Exception as e:
            return jsonify({"error": "runtime_error", "message": f"{type(e).__name__}: {e}", "console": print_buffer["text"]}), 400

    qc = safe_locals.get("qc")
    if not isinstance(qc, QuantumCircuit):
        return (
            jsonify({
                "error": "no_circuit",
                "message": "Your code needs to assign a QuantumCircuit to a variable named `qc`.",
                "console": print_buffer["text"],
            }),
            400,
        )
    if qc.num_qubits > _MAX_QUBITS:
        return jsonify({"error": "too_many_qubits", "message": f"Max {_MAX_QUBITS} qubits in this playground.", "console": print_buffer["text"]}), 400
    if len(qc.data) > _MAX_GATES:
        return jsonify({"error": "too_many_gates", "message": f"Max {_MAX_GATES} operations.", "console": print_buffer["text"]}), 400
    has_measurement = any(instr.operation.name == "measure" for instr in qc.data)
    if not has_measurement:
        return (
            jsonify({
                "error": "no_measurement",
                "message": "Add qc.measure_all() or qc.measure(...) so there's something to read out.",
                "console": print_buffer["text"],
            }),
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
            "console": print_buffer["text"],
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


def _build_circuit_from_code(code):
    """Shared by /api/run-code and /api/export-qasm: validates + runs
    restricted code and returns the resulting QuantumCircuit (raises
    _CodeValidationError / _TooManyOperationsError / etc. same as
    api_run_code — callers translate those to HTTP responses)."""
    compiled = _validate_circuit_code(code)
    safe_builtins = {
        "range": range, "len": len, "abs": abs, "min": min, "max": max,
        "int": int, "float": float, "str": str, "bool": bool, "enumerate": enumerate,
        "print": lambda *a, **kw: None, "input": _make_sandboxed_input([]),
    }
    safe_globals = {"__builtins__": safe_builtins, "QuantumCircuit": QuantumCircuit, "pi": math.pi}
    safe_locals = {}
    with _RUN_CODE_LOCK:
        if hasattr(signal, "SIGALRM"):
            def _on_timeout(signum, frame):
                raise TimeoutError("Code took too long to run (3s limit).")

            old_handler = signal.signal(signal.SIGALRM, _on_timeout)
            signal.alarm(3)
            try:
                _run_validated_circuit(compiled, safe_globals, safe_locals)
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        else:
            _run_validated_circuit(compiled, safe_globals, safe_locals)
    qc = safe_locals.get("qc")
    if not isinstance(qc, QuantumCircuit):
        raise _CodeValidationError("Your code needs to assign a QuantumCircuit to a variable named `qc`.")
    if qc.num_qubits > _MAX_QUBITS:
        raise _CodeValidationError(f"Max {_MAX_QUBITS} qubits in this playground.")
    if len(qc.data) > _MAX_GATES:
        raise _CodeValidationError(f"Max {_MAX_GATES} operations.")
    return qc


@app.route("/api/export-qasm", methods=["POST"])
def api_export_qasm():
    # No auth required — exporting your own in-progress editor content
    # isn't a write, just a different serialization of what you
    # already have on screen.
    data = request.get_json(silent=True) or {}
    try:
        qc = _build_circuit_from_code(data.get("code", ""))
        qasm_text = qasm2.dumps(qc)
    except _CodeValidationError as e:
        return jsonify({"error": "invalid_code", "message": str(e)}), 400
    except (_TooManyOperationsError, _TooManyStepsError, TimeoutError, Exception) as e:
        return jsonify({"error": "runtime_error", "message": f"{type(e).__name__}: {e}"}), 400
    return jsonify({"qasm": qasm_text})


# Maps a Qiskit instruction name (as it comes back from qasm2.loads())
# to how it's written in our restricted grammar. Anything not in this
# map means the QASM used a gate we don't support in the editor — the
# import is rejected with a clear message rather than silently
# dropping the gate, since dropping it would change what the circuit
# actually does.
_QASM_GATE_TO_METHOD = {
    "h": "h", "x": "x", "y": "y", "z": "z", "rx": "rx", "ry": "ry", "rz": "rz",
    "cx": "cx", "measure": "measure", "barrier": "barrier", "id": None,  # 'id' (identity) is silently dropped
}


@app.route("/api/import-qasm", methods=["POST"])
def api_import_qasm():
    # No auth required, same reasoning as export — converts pasted-in
    # QASM into our restricted-grammar Python, which is NOT trusted
    # output: it's placed back into the editor as plain text and, if
    # run, goes through the exact same _validate_circuit_code AST
    # validator as anything else typed in by hand. This endpoint's own
    # job is just building a fair, readable translation and rejecting
    # anything it can't safely translate — not enforcing the sandbox
    # (that still happens on every actual run).
    data = request.get_json(silent=True) or {}
    qasm_text = data.get("qasm", "")
    if not isinstance(qasm_text, str) or not qasm_text.strip():
        return jsonify({"error": "bad_request", "message": "No QASM submitted."}), 400
    if len(qasm_text) > 8000:
        return jsonify({"error": "bad_request", "message": "QASM is too long (max 8000 characters)."}), 400
    try:
        qc = qasm2.loads(qasm_text)
    except Exception as e:
        return jsonify({"error": "invalid_qasm", "message": f"Could not parse QASM: {e}"}), 400

    if qc.num_qubits > _MAX_QUBITS:
        return jsonify({"error": "too_many_qubits", "message": f"Max {_MAX_QUBITS} qubits in this playground."}), 400
    if len(qc.data) > _MAX_GATES:
        return jsonify({"error": "too_many_gates", "message": f"Max {_MAX_GATES} operations."}), 400

    lines = [f"qc = QuantumCircuit({qc.num_qubits}, {qc.num_clbits})"]
    for instr in qc.data:
        name = instr.operation.name
        if name not in _QASM_GATE_TO_METHOD:
            return jsonify({
                "error": "unsupported_gate",
                "message": f"This QASM uses '{name}', which isn't one of the gates this editor supports "
                           f"({', '.join(sorted(m for m in set(_QASM_GATE_TO_METHOD.values()) if m))}).",
            }), 400
        method = _QASM_GATE_TO_METHOD[name]
        if method is None:
            continue  # identity gate — no-op, safe to drop
        qubit_indices = [qc.find_bit(q).index for q in instr.qubits]
        if method == "measure":
            clbit_index = qc.find_bit(instr.clbits[0]).index
            lines.append(f"qc.measure({qubit_indices[0]}, {clbit_index})")
        elif method == "cx":
            lines.append(f"qc.cx({qubit_indices[0]}, {qubit_indices[1]})")
        elif method == "barrier":
            lines.append("qc.barrier()")
        elif method in ("rx", "ry", "rz"):
            theta = instr.operation.params[0]
            lines.append(f"qc.{method}({theta!r}, {qubit_indices[0]})")
        else:
            lines.append(f"qc.{method}({qubit_indices[0]})")

    return jsonify({"code": "\n".join(lines)})


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


# ======================================================================
# Shareable circuits + embeds + Playground gallery
# (anonymous-visitor branch — futureplans.md)
# ======================================================================

MAX_SHARE_TITLE = 120


@app.route("/api/share", methods=["POST"])
@csrf_protect
def api_create_share():
    # No @login_required — sharing something you built shouldn't
    # require an account (matches the Sandbox/demos themselves, which
    # are open to everyone). CSRF is still enforced: this writes data,
    # and csrf_protect's token check doesn't require a signed-in
    # session, just a same-origin request with the page's own token.
    data = request.get_json(silent=True) or {}
    code = data.get("code", "")
    title = (data.get("title") or "").strip()[:MAX_SHARE_TITLE] or None
    public = bool(data.get("public"))
    try:
        _validate_circuit_code(code)
    except _CodeValidationError as e:
        return jsonify({"error": "invalid_code", "message": str(e)}), 400
    author_id = int(current_user.id) if current_user.is_authenticated else None
    shared = db.create_shared_circuit(code, title=title, author_user_id=author_id, public=public)
    return jsonify(
        {
            "hash": shared["hash"],
            "url": url_for("view_shared_circuit", hash_=shared["hash"]),
            "embed_url": url_for("embed_shared_circuit", hash_=shared["hash"], _external=True),
        }
    )


@app.route("/share/<hash_>")
def view_shared_circuit(hash_):
    shared = db.get_shared_circuit(hash_)
    if shared is None:
        abort(404)
    db.bump_shared_circuit_views(hash_)
    author = db.get_user_by_id(shared["author_user_id"]) if shared["author_user_id"] else None
    return render_template(
        "share-circuit.html",
        active_page="gallery",
        shared=shared,
        author_name=(author["name"] if author else None),
        embed_url=url_for("embed_shared_circuit", hash_=hash_, _external=True),
    )


@app.route("/embed/circuit/<hash_>")
def embed_shared_circuit(hash_):
    # Deliberately minimal, matching /embed/coin-flip and
    # /embed/two-qubit — no sidebar/topbar, meant to sit inside someone
    # else's <iframe>.
    shared = db.get_shared_circuit(hash_)
    if shared is None:
        abort(404)
    db.bump_shared_circuit_views(hash_)
    return render_template("embed-circuit.html", shared=shared)


@app.route("/gallery")
def gallery():
    # Playground gallery (tinkerer branch): public, opt-in shared
    # circuits — lower stakes than publishing a whole lesson, and
    # doesn't require a creator account, just the "list publicly"
    # checkbox at share time.
    return render_template("gallery.html", active_page="gallery", circuits=db.list_public_shared_circuits())


# ======================================================================
# "Confused here" (student-learning branch)
# ======================================================================

@app.route("/api/confusion", methods=["POST"])
@csrf_protect
def api_report_confusion():
    # No @login_required — an anonymous visitor on an open lesson
    # (QM Basics, Single Qubit) can still flag a step; user_id is just
    # None in that case. This is a one-way signal with no reply, so
    # there's nothing sensitive being tied to an identity either way.
    data = request.get_json(silent=True) or {}
    lesson_id = data.get("lesson_id")
    step_key = data.get("step_key")
    if not lesson_id or not step_key or not isinstance(lesson_id, str) or not isinstance(step_key, str):
        return jsonify({"error": "bad_request"}), 400
    if len(lesson_id) > 100 or len(step_key) > 100:
        return jsonify({"error": "bad_request"}), 400
    user_id = int(current_user.id) if current_user.is_authenticated else None
    db.record_confusion_report(lesson_id, step_key, user_id)
    return jsonify({"ok": True})


# ======================================================================
# Forking + draft/preview mode (creator branch)
# ======================================================================

@app.route("/api/lessons/<int:lesson_id>/fork", methods=["POST"])
@login_required
@csrf_protect
def api_fork_lesson(lesson_id):
    if not current_user.can_create_lessons:
        return jsonify({"error": "forbidden", "message": "Verified creator account required."}), 403
    source = db.get_custom_lesson_by_id(lesson_id)
    if source is None or not source["published"]:
        return jsonify({"error": "not_found", "message": "That lesson isn't available to fork."}), 404
    forked = db.fork_custom_lesson(source, int(current_user.id))
    return jsonify({"slug": forked["slug"], "url": url_for("lesson_creator", edit=forked["id"])})


@app.route("/api/lessons/<int:lesson_id>/preview-link", methods=["POST"])
@login_required
@csrf_protect
def api_generate_preview_link(lesson_id):
    """Draft/preview mode: generates (or rotates) an unguessable
    preview link for a lesson the requester owns, so it can be shared
    for feedback before publishing — without making it publicly
    published or visible only to the author. Works on both drafts and
    already-published lessons (harmless either way — see
    set_lesson_preview_token's docstring)."""
    lesson, err = _get_own_lesson_or_403(lesson_id)
    if lesson is None:
        return err
    token = secrets.token_urlsafe(16)
    db.set_lesson_preview_token(lesson_id, token)
    return jsonify({"preview_url": url_for("custom_lesson_preview", slug=lesson["slug"], token=token)})


@app.route("/lessons/custom/<slug>/preview/<token>")
def custom_lesson_preview(slug, token):
    lesson = db.get_custom_lesson_by_preview_token(slug, token)
    if lesson is None:
        abort(404)
    return _render_custom_lesson(lesson, is_preview=True)


# ======================================================================
# Lesson analytics for creators (creator branch)
# ======================================================================

@app.route("/api/lessons/<int:lesson_id>/analytics")
@login_required
def api_lesson_analytics(lesson_id):
    lesson, err = _get_own_lesson_or_403(lesson_id)
    if lesson is None:
        return err
    steps = json.loads(lesson["steps_json"])
    counts, total_visitors = db.get_lesson_step_completion_counts(f"custom-{lesson['slug']}")
    per_step = []
    for i, step in enumerate(steps):
        key = f"step{i}"
        per_step.append({"index": i, "title": step.get("title", f"Step {i+1}"), "count": counts.get(key, 0)})
    return jsonify({"total_visitors": total_visitors, "steps": per_step})


if __name__ == "__main__":
    # debug=True auto-reloads on file changes — turn it off before deploying.
    app.run(debug=True, host="0.0.0.0", port=5000)
