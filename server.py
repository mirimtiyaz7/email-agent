"""
Email Triage - Flask backend (works with cPanel "Setup Python App").
Local run:  python server.py     then open http://127.0.0.1:5000
Needs email_triage_gemini.py and .env in the same folder.
"""
import time
import threading

from flask import Flask, jsonify, render_template, request

from email_triage_gemini import DEMO_EMAILS, triage

app = Flask(__name__)

# ---- Simple protection so strangers cannot burn your free API quota ----
RATE_LIMIT = 20        # requests allowed...
RATE_WINDOW = 600      # ...per 10 minutes per visitor
_hits = {}
_lock = threading.Lock()


def client_ip():
    forwarded = request.headers.get("X-Forwarded-For", request.remote_addr or "")
    return forwarded.split(",")[0].strip()


def rate_limited():
    now = time.time()
    ip = client_ip()
    with _lock:
        recent = [t for t in _hits.get(ip, []) if now - t < RATE_WINDOW]
        if len(recent) >= RATE_LIMIT:
            _hits[ip] = recent
            return True
        recent.append(now)
        _hits[ip] = recent
    return False


# Demo results are cached so repeated visitors do not use extra API calls
_demo_cache = None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/demo")
def api_demo():
    global _demo_cache
    if rate_limited():
        return jsonify({"error": "Too many requests. Please wait a few minutes."}), 429
    if _demo_cache is None:
        results = []
        for m in DEMO_EMAILS:
            r = triage(m)
            r["from"], r["subject"] = m["from"], m["subject"]
            results.append(r)
        results.sort(key=lambda r: r["urgency"], reverse=True)
        _demo_cache = results
    return jsonify(_demo_cache)


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    if rate_limited():
        return jsonify({"error": "Too many requests. Please wait a few minutes."}), 429
    data = request.get_json(silent=True) or {}
    mail = {
        "from": str(data.get("from", ""))[:200],
        "subject": str(data.get("subject", ""))[:300],
        "body": str(data.get("body", ""))[:3000],
    }
    if not mail["body"].strip():
        return jsonify({"error": "Email body is empty."}), 400
    r = triage(mail)
    r["from"], r["subject"] = mail["from"], mail["subject"]
    return jsonify(r)


if __name__ == "__main__":
    app.run(debug=True)
