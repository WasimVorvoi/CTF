import json
import secrets
import time
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, request

DATA_DIR = Path(__file__).parent / "data"
INTERNAL_KEY = "escape_shared_key"

app = Flask(__name__)
escape_sessions = {}
escape_states = {}


def _read_json(filename, default):
    path = DATA_DIR / filename
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(filename, payload):
    path = DATA_DIR / filename
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def _find_user_by_token(token):
    users = _read_json("users.json", [])
    return next((user for user in users if user.get("token") == token), None)


def _find_user_by_username(username):
    users = _read_json("users.json", [])
    return next((user for user in users if user.get("username") == username), None)


def _update_user(updated_user):
    users = _read_json("users.json", [])
    updated = []
    for user in users:
        if user.get("id") == updated_user.get("id"):
            updated.append(updated_user)
        else:
            updated.append(user)
    _write_json("users.json", updated)


def _get_team(team_id):
    teams = _read_json("teams.json", [])
    return next((team for team in teams if team.get("id") == team_id), None)


def _update_team(updated_team):
    teams = _read_json("teams.json", [])
    updated = []
    for team in teams:
        if team.get("id") == updated_team.get("id"):
            updated.append(updated_team)
        else:
            updated.append(team)
    _write_json("teams.json", updated)


def _ensure_team_score(team_id):
    team_answers = _read_json("team_answers.json", {})
    if team_id not in team_answers:
        team_answers[team_id] = {"answers": {}, "score": 0}
        _write_json("team_answers.json", team_answers)
    return team_answers


def _event_end_time():
    timer = _read_json("timer.json", {"end_time": None})
    return timer.get("end_time")


def is_event_active():
    end_time = _event_end_time()
    if end_time is None:
        return True
    return time.time() < end_time


def authenticate_token(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        token = request.headers.get("Authorization")
        if not token:
            return jsonify({"error": "Missing token"}), 401
        user = _find_user_by_token(token)
        if not user:
            return jsonify({"error": "Invalid token"}), 401
        return func(user, *args, **kwargs)

    return wrapper


def require_admin(func):
    @wraps(func)
    def wrapper(user, *args, **kwargs):
        if user.get("role") != "admin":
            return jsonify({"error": "Admin access required"}), 403
        return func(user, *args, **kwargs)

    return wrapper


@app.route("/api/signup", methods=["POST"])
def signup():
    payload = request.get_json(force=True)
    username = payload.get("username", "").strip()
    password = payload.get("password", "")
    role = payload.get("role", "student")
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    if _find_user_by_username(username):
        return jsonify({"error": "Username already exists"}), 400
    users = _read_json("users.json", [])
    user = {
        "id": secrets.token_hex(8),
        "username": username,
        "password": password,
        "role": role,
        "team_id": None,
        "token": None,
        "secret1": False,
    }
    users.append(user)
    _write_json("users.json", users)
    return jsonify({"message": "User created"}), 201


@app.route("/api/login", methods=["POST"])
def login():
    payload = request.get_json(force=True)
    username = payload.get("username", "").strip()
    password = payload.get("password", "")
    user = _find_user_by_username(username)
    if not user or user.get("password") != password:
        return jsonify({"error": "Invalid credentials"}), 401
    token = secrets.token_hex(32)
    user["token"] = token
    _update_user(user)
    return jsonify({"token": token, "user": user})


@app.route("/api/questions", methods=["GET"])
@authenticate_token
def questions(user):
    questions = _read_json("questions.json", [])
    team_answers = _read_json("team_answers.json", {})
    team_id = user.get("team_id")
    answers = team_answers.get(team_id, {}).get("answers", {}) if team_id else {}
    response = []
    for question in questions:
        qid = question.get("id")
        answer = answers.get(qid)
        status = "unanswered"
        if answer:
            status = "correct" if answer.get("correct") else "incorrect"
        response.append({**question, "status": status})
    return jsonify(response)


@app.route("/api/submit", methods=["POST"])
@authenticate_token
def submit(user):
    if not is_event_active():
        return jsonify({"error": "Event over"}), 403
    payload = request.get_json(force=True)
    qid = payload.get("question_id")
    answer = payload.get("answer", "")
    team_id = user.get("team_id")
    if not team_id:
        return jsonify({"error": "Join a team first"}), 400
    disabled = _read_json("disabled_questions.json", {})
    cooldowns = disabled.get(team_id, {})
    until = cooldowns.get(qid)
    if until and time.time() < until:
        return jsonify({"error": "Cooldown active"}), 429
    questions = _read_json("questions.json", [])
    question = next((q for q in questions if q.get("id") == qid), None)
    if not question:
        return jsonify({"error": "Question not found"}), 404
    correct = answer.strip().lower() == str(question.get("answer", "")).strip().lower()
    submissions = _read_json("submissions.json", [])
    submissions.append(
        {
            "id": secrets.token_hex(8),
            "question_id": qid,
            "team_id": team_id,
            "user_id": user.get("id"),
            "answer": answer,
            "correct": correct,
            "timestamp": time.time(),
        }
    )
    _write_json("submissions.json", submissions)
    team_answers = _ensure_team_score(team_id)
    entry = team_answers[team_id]
    entry.setdefault("answers", {})[qid] = {"answer": answer, "correct": correct}
    if correct:
        entry["score"] = entry.get("score", 0) + int(question.get("points", 0))
    else:
        disabled.setdefault(team_id, {})[qid] = time.time() + 60
        _write_json("disabled_questions.json", disabled)
    _write_json("team_answers.json", team_answers)
    return jsonify({"correct": correct})


@app.route("/api/leaderboard", methods=["GET"])
@authenticate_token
def leaderboard(_user):
    teams = _read_json("teams.json", [])
    team_answers = _read_json("team_answers.json", {})
    results = []
    for team in teams:
        team_id = team.get("id")
        score = team_answers.get(team_id, {}).get("score", 0)
        results.append({"team_id": team_id, "name": team.get("name"), "score": score})
    results.sort(key=lambda item: item["score"], reverse=True)
    return jsonify(results)


@app.route("/api/teams", methods=["POST"])
@authenticate_token
def create_team(user):
    payload = request.get_json(force=True)
    name = payload.get("name", "").strip()
    join_type = payload.get("join_type", "anyone")
    if not name:
        return jsonify({"error": "Team name required"}), 400
    teams = _read_json("teams.json", [])
    team = {
        "id": secrets.token_hex(6),
        "name": name,
        "join_type": join_type,
        "members": [user.get("id")],
        "can_play_escape": True,
    }
    teams.append(team)
    _write_json("teams.json", teams)
    user["team_id"] = team["id"]
    _update_user(user)
    _ensure_team_score(team["id"])
    return jsonify(team), 201


@app.route("/api/teams/join", methods=["POST"])
@authenticate_token
def join_team(user):
    payload = request.get_json(force=True)
    team_id = payload.get("team_id")
    teams = _read_json("teams.json", [])
    team = next((t for t in teams if t.get("id") == team_id), None)
    if not team:
        return jsonify({"error": "Team not found"}), 404
    if len(team.get("members", [])) >= 4:
        return jsonify({"error": "Team full"}), 400
    if user.get("id") not in team["members"]:
        team["members"].append(user.get("id"))
    _update_team(team)
    user["team_id"] = team_id
    _update_user(user)
    _ensure_team_score(team_id)
    return jsonify({"message": "Joined team"})


@app.route("/api/team/<team_id>/leave", methods=["POST"])
@authenticate_token
def leave_team(user, team_id):
    team = _get_team(team_id)
    if not team:
        return jsonify({"error": "Team not found"}), 404
    if user.get("id") in team.get("members", []):
        team["members"].remove(user.get("id"))
        _update_team(team)
    user["team_id"] = None
    _update_user(user)
    return jsonify({"message": "Left team"})


@app.route("/api/admin/timer", methods=["POST"])
@authenticate_token
@require_admin
def admin_timer(_user):
    payload = request.get_json(force=True)
    timer = _read_json("timer.json", {"end_time": None})
    if payload.get("setSeconds") is not None:
        timer["end_time"] = time.time() + int(payload["setSeconds"])
    elif payload.get("additionalSeconds") is not None:
        end_time = timer.get("end_time") or time.time()
        timer["end_time"] = end_time + int(payload["additionalSeconds"])
    _write_json("timer.json", timer)
    return jsonify(timer)


@app.route("/api/admin/announcement", methods=["POST"])
@authenticate_token
@require_admin
def admin_announcement(_user):
    payload = request.get_json(force=True)
    announcement = {"message": payload.get("message", "")}
    _write_json("announcement.json", announcement)
    return jsonify(announcement)


@app.route("/api/admin/team-score", methods=["POST"])
@authenticate_token
@require_admin
def admin_team_score(_user):
    payload = request.get_json(force=True)
    team_id = payload.get("team_id")
    score = int(payload.get("score", 0))
    team_answers = _ensure_team_score(team_id)
    team_answers[team_id]["score"] = score
    _write_json("team_answers.json", team_answers)
    return jsonify({"team_id": team_id, "score": score})


@app.route("/api/admin/team-toggle-escape/<team_id>", methods=["POST"])
@authenticate_token
@require_admin
def admin_toggle_escape(_user, team_id):
    team = _get_team(team_id)
    if not team:
        return jsonify({"error": "Team not found"}), 404
    team["can_play_escape"] = not team.get("can_play_escape", True)
    _update_team(team)
    return jsonify({"team_id": team_id, "can_play_escape": team["can_play_escape"]})


@app.route("/api/internal/award", methods=["POST"])
def internal_award():
    payload = request.get_json(force=True)
    if payload.get("key") != INTERNAL_KEY:
        return jsonify({"error": "Unauthorized"}), 403
    team_id = payload.get("team_id")
    points = int(payload.get("points", 0))
    team_answers = _ensure_team_score(team_id)
    team_answers[team_id]["score"] = team_answers[team_id].get("score", 0) + points
    _write_json("team_answers.json", team_answers)
    return jsonify({"team_id": team_id, "points": points})


@app.route("/api/deduct-points", methods=["POST"])
def deduct_points():
    payload = request.get_json(force=True)
    if payload.get("key") != INTERNAL_KEY:
        return jsonify({"error": "Unauthorized"}), 403
    team_id = payload.get("team_id")
    points = int(payload.get("points", 0))
    team_answers = _ensure_team_score(team_id)
    team_answers[team_id]["score"] = max(team_answers[team_id].get("score", 0) - points, 0)
    _write_json("team_answers.json", team_answers)
    return jsonify({"team_id": team_id, "points": points})


@app.route("/api/validate-secret", methods=["POST"])
@authenticate_token
def validate_secret(user):
    payload = request.get_json(force=True)
    secret = payload.get("secret", "")
    if secret != "Wasim":
        team_id = user.get("team_id")
        if team_id:
            team_answers = _ensure_team_score(team_id)
            team_answers[team_id]["score"] = max(team_answers[team_id].get("score", 0) - 3, 0)
            _write_json("team_answers.json", team_answers)
        return jsonify({"valid": False}), 400
    return jsonify({"valid": True})


@app.route("/api/secret-unlock", methods=["POST"])
@authenticate_token
def secret_unlock(user):
    user["secret1"] = True
    _update_user(user)
    return jsonify({"secret1": True})


@app.route("/api/escape/new", methods=["GET"])
@authenticate_token
def escape_new(user):
    team_id = user.get("team_id")
    if not team_id:
        return jsonify({"error": "Join a team first"}), 400
    team = _get_team(team_id)
    if not team or not team.get("can_play_escape", True):
        return jsonify({"error": "Escape not allowed"}), 403
    session_id = secrets.token_hex(12)
    puzzles = {
        "r1": {"prompt": "Factor 1001733993063167141", "answer": "1000003"},
        "r2": {"prompt": "Decode 3-byte repeating XOR cipher", "answer": "xor_answer"},
        "r3": {"prompt": "Decode base64+rot13", "answer": "base64_rot13"},
    }
    escape_sessions[session_id] = {"team_id": team_id, "puzzles": puzzles}
    return jsonify({"sid": session_id, "puzzles": {key: value["prompt"] for key, value in puzzles.items()}})


@app.route("/api/escape/state", methods=["POST"])
@authenticate_token
def escape_state(user):
    payload = request.get_json(force=True)
    escape_states[user.get("id")] = payload
    return jsonify({"saved": True})


@app.route("/api/escape/complete", methods=["POST"])
@authenticate_token
def escape_complete(user):
    team_id = user.get("team_id")
    if not team_id:
        return jsonify({"error": "Join a team first"}), 400
    team_answers = _ensure_team_score(team_id)
    team_answers[team_id]["score"] = team_answers[team_id].get("score", 0) + 100
    _write_json("team_answers.json", team_answers)
    team = _get_team(team_id)
    if team:
        team["can_play_escape"] = False
        _update_team(team)
    return jsonify({"awarded": 100})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5500, debug=True)
