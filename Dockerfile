# Qubit Sandbox — Dockerfile
#
# Build:  docker build -t qubit-sandbox .
# Run:    docker run -p 5000:5000 qubit-sandbox
# Then open http://localhost:5000
#
# This runs the app with gunicorn (production WSGI server), not
# Flask's built-in dev server — that's the point of containerizing it.

FROM python:3.12-slim

WORKDIR /app

# Install dependencies first so Docker can cache this layer separately
# from the app code — rebuilds are fast unless requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

# Bind to 0.0.0.0 so the container's port is reachable from outside it.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app:app"]
