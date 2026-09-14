"""
Qubit Sandbox — Flask app

Run it with:
    python app.py

Then open http://localhost:6969 in a browser.

There's no database. Each route below renders one template — nearly
all the "quantum simulation" logic lives in static/js/ and runs in the
visitor's browser, not here. Python's job is just: match a URL to a
page, and hand every page the same sidebar nav data via NAV_ITEMS.
"""

from flask import Flask, render_template

app = Flask(__name__)

# Single source of truth for the sidebar. base.html loops over this,
# so adding a new lab page later is: add a route below + one entry here.
NAV_ITEMS = [
    {"key": "dashboard", "label": "Dashboard", "href": "/dashboard", "icon": "grid"},
    {"key": "single", "label": "Single Qubit", "href": "/single-qubit", "icon": "atom"},
    {"key": "two", "label": "Two Qubits", "href": "/two-qubit", "icon": "twocircle"},
    {"key": "physical", "label": "Physical Qubit", "href": "/physical-qubit", "icon": "chip"},
    {"key": "hardware", "label": "Hardware Lab", "href": "/hardware-lab", "icon": "cpu", "badge": "Soon"},
    {"key": "reality", "label": "Reality Check", "href": "/reality-check", "icon": "chart"},
]


@app.context_processor
def inject_nav():
    """Makes `nav_items` available in every template without passing it
    explicitly in each render_template() call below."""
    return {"nav_items": NAV_ITEMS}


@app.route("/")
def landing():
    # Standalone marketing/introduction page — does NOT use the sidebar shell.
    return render_template("landing.html")


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", active_page="dashboard")


@app.route("/single-qubit")
def single_qubit():
    return render_template("single-qubit.html", active_page="single")


@app.route("/two-qubit")
def two_qubit():
    return render_template("two-qubit.html", active_page="two")


@app.route("/physical-qubit")
def physical_qubit():
    return render_template("physical-qubit.html", active_page="physical")


@app.route("/hardware-lab")
def hardware_lab():
    # Scaffolded on purpose, content intentionally left as TODOs —
    # see futureplans.md.
    return render_template("hardware-lab.html", active_page="hardware")


@app.route("/reality-check")
def reality_check():
    return render_template("reality-check.html", active_page="reality")


if __name__ == "__main__":
    # debug=True auto-reloads on file changes — turn it off before deploying.
    app.run(debug=True, host="0.0.0.0", port=6969)
