"""
Qubit Sandbox — Flask app

Run it with:
    python app.py

Then open http://localhost:6969 in a browser.

There's no database and no build step. Each route below just renders
one HTML file from templates/ — all the actual "quantum simulation"
logic lives in static/js/ and runs in the visitor's browser, not here.
"""

from flask import Flask, render_template

app = Flask(__name__)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/single-qubit")
def single_qubit():
    return render_template("single-qubit.html")


@app.route("/two-qubit")
def two_qubit():
    return render_template("two-qubit.html")


@app.route("/physical-qubit")
def physical_qubit():
    return render_template("physical-qubit.html")


@app.route("/reality-check")
def reality_check():
    return render_template("reality-check.html")


if __name__ == "__main__":
    # debug=True auto-reloads when you edit a template or static file —
    # turn it off before you actually deploy this anywhere public.
    app.run(debug=True, port=6969)
