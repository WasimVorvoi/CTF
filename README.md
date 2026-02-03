# V7Online CTF Platform Overview

V7Online is a Capture The Flag (CTF) competition platform built with a Flask (Python) backend and a vanilla HTML5/CSS3/JavaScript frontend, featuring a unique chess-based "Escape Challenge" mini-game powered by the chess.js library and the Stockfish chess engine (served via a Node.js Express wrapper or native binary).

## Backend (Flask)

- **Main server**: `server.py` (~2110 lines) runs on port **5500** and manages all core functionality.
- **Data storage**: JSON files in `data/`:
  - `users.json`, `questions.json`, `submissions.json`, `teams.json`, `team_answers.json`,
    `disabled_questions.json`, `timer.json`, `announcement.json`
- **Authentication**: 32-byte secure session tokens stored in `localStorage` on the client and validated via an `Authorization` header.
- **Role-based access control**: `admin` and `student` roles enforced through Python decorators (`@authenticate_token`, `@require_admin`).

### Core Student Flows

- **Auth**:
  - `POST /api/login`
  - `POST /api/signup`
  - Returns a token and user object.
- **Questions**:
  - `GET /api/questions` returns per-question status (correct/pending/incorrect/unanswered) computed across all team members.
  - `POST /api/submit` auto-grades via case-insensitive string comparison and awards points to the team on correct answers.
  - Incorrect answers impose a **1-minute cooldown** per team (tracked in `disabled_questions.json`).
- **Leaderboard**:
  - `GET /api/leaderboard` aggregates team scores from `team_answers.json` and sorts descending.
- **Teams**:
  - `POST /api/teams` to create teams with types `anyone`/`specified`/`solo`.
  - `POST /api/teams/join` to join, max 4 members.
  - `POST /api/team/<id>/leave` to leave.

### Admin Panel

The admin panel (`admin.html`, ~323 lines) provides:

- CRUD for users and questions
- Pending submission grading (accept/reject)
- Timer control:
  - `POST /api/admin/timer` with `additionalSeconds` or `setSeconds`
- Global announcements:
  - `POST /api/admin/announcement`
- Team score setting:
  - `POST /api/admin/team-score`
- Escape permission toggling per team:
  - `POST /api/admin/team-toggle-escape/<team_id>`
- Bulk resets for scores/submissions/escape permissions
- A danger zone for destructive operations

### Event Timer

Enforced server-side via `is_event_active()` which checks a persisted `timer.json` end time. When expired:

- Submissions are rejected.
- Client UI disables all inputs and shows an **"Event Over"** overlay.

## Escape Challenge (Chess Mini-Game)

The Escape Challenge begins when a student clicks play:

- `GET /api/escape/new` validates the team's `can_play_escape` flag and returns **three server-generated puzzles**:
  - **r1**: factor a large prime product `1001733993063167141` with answer `1000003`
  - **r2**: decode a 3-byte repeating XOR cipher
  - **r3**: decode base64 + rot13
- Answers are stored server-side in `escape_sessions[sid]`.
- Opens `escape.html` (~990 lines) in a new window:
  - 8x8 board rendered with Unicode pieces
  - User plays **white** against Stockfish **black**
  - Each move validated by chess.js
  - Bot move fetched via `POST /engine/bestmove`
    - Tries Node.js wrapper on ports **5501-5510**
    - Falls back to spawning native Stockfish with UCI protocol at **depth 8** and **5s timeout**
  - Game state (FEN, timers, level, completion) saved every 2 seconds via `POST /api/escape/state`
  - Each player has a **300-second clock**
- On **checkmate**, player is awarded **100 points** via `POST /api/escape/complete` (or fallback `POST /api/internal/award` with shared `INTERNAL_KEY`)
- On **loss/draw/timeout/resignation**, team is marked as having played and can no longer attempt the challenge.

## Escape Service (Secondary Flask)

A secondary Flask service (`escape.py`, ~128 lines) runs on port **5600**:

- `POST /submit` handles escape submissions.
- Counts attempts per token; deducts **10 points every 10 failed attempts** via `/api/deduct-points`.
- Awards **150 points** on correct secret payload `"award_me_please_123"` by calling `/api/internal/award` with the shared internal key.

## Frontend

### Main UI (`index.html`, ~790 lines)

- Login/signup form
- Student dashboard with question cards:
  - checkmark = completed
  - hourglass = analyzing
  - warning = retry
  - dot = active
- Leaderboard rendered as animated bar charts:
  - gold/silver/bronze gradients for top 3
  - green glow for current user
  - auto-refreshes every 1 second
- Matrix-style falling binary canvas animation
- Glitch text effects
- Secret password section:
  - Entering `"Wasim"` via `POST /api/validate-secret` redirects to `secret.html`
  - Wrong attempts deduct **3 points**
  - `POST /api/secret-unlock` sets the user’s `Secret1` flag to true

### Team Dashboard (`team.html`, ~300 lines)

- Tabbed interface (TEAM/QUESTIONS/LEADERBOARD)
- Displays team members with scores
- **"Play Chess Challenge"** button
- Invite link copying
- Team progress metrics

### Team Creation (`teams.html`, ~200 lines)

- Lists available public teams
- Modal for creating teams with join-type options

## Styling (`static/styles.css`, ~1000+ lines)

- High-contrast neon cyber aesthetic:
  - dark backgrounds `#05060a`, `#0b0e16`
  - neon accents `#00ffe1`, `#33ff99`
- CSS grid layouts
- Terminal panel styling
- Glow effects
- Custom scrollbars
- Glitch animations
- Pulse effects
- Hue-shift animations
- Responsive media queries

## Stockfish Engine Wrapper

The Stockfish Node.js engine wrapper (`stockfish_engine/engine.js`) runs an Express server with CORS enabled:

- Manages a pool of Stockfish WASM workers
- Exposes `/health` and `POST /bestmove`

## Security/Defaults

- Passwords stored in plaintext JSON files.
- Hard-coded defaults:
  - `admin/admin123`
  - Secret password: `"Wasim"`
  - Internal key: `"escape_shared_key"`
- Test users:
  - Wasim/wasim25wasim
  - comp/321321
  - sriharsha/Gonner
  - Dev/safsadsa
  - water/water

## Logging & Error Handling

- Comprehensive request/response logging via `RotatingFileHandler` (5MB max, 3 backups) with sensitive field masking.
- Global exception handling returns 500 JSON errors.
- SPA-style routing: unmatched paths fall back to `index.html`.

## Deployment

Deployment is orchestrated via `run_all.bat` which:

- Activates a Python virtual environment
- Starts the main Flask server on **5500**
- Starts the escape service on **5600**
- Starts the Node engine service on **5501+**

The system is designed for local Windows execution supporting team-based scoring, real-time leaderboards, timed events, and a chess-based challenge mechanic.
