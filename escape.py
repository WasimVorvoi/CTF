import json
import os
from pathlib import Path

import requests
from flask import Flask, jsonify, request

DATA_DIR = Path(__file__).parent / "data"
ATTEMPTS_FILE = DATA_DIR / "escape_attempts.json"
MAIN_SERVER = os.environ.get("MAIN_SERVER_URL", "http://localhost:5500")
INTERNAL_KEY = "escape_shared_key"

app = Flask(__name__)


def _read_attempts():
    if not ATTEMPTS_FILE.exists():
        return {}
    with ATTEMPTS_FILE.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_attempts(payload):
    with ATTEMPTS_FILE.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


@app.route("/submit", methods=["POST"])
def submit_escape():
    payload = request.get_json(force=True)
    token = payload.get("token")
    secret = payload.get("secret")
    if not token:
        return jsonify({"error": "Missing token"}), 400
    attempts = _read_attempts()
    attempts.setdefault(token, 0)
    if secret == "award_me_please_123":
        requests.post(
            f"{MAIN_SERVER}/api/internal/award",
            json={"key": INTERNAL_KEY, "team_id": payload.get("team_id"), "points": 150},
            timeout=5,
        )
        return jsonify({"status": "awarded"})
    attempts[token] += 1
    if attempts[token] % 10 == 0:
        requests.post(
            f"{MAIN_SERVER}/api/deduct-points",
            json={"key": INTERNAL_KEY, "team_id": payload.get("team_id"), "points": 10},
            timeout=5,
        )
    _write_attempts(attempts)
    return jsonify({"status": "incorrect", "attempts": attempts[token]}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5600, debug=True)
