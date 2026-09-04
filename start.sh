#!/usr/bin/env bash
#
# Wreckognise -- one-command local start (macOS / Linux / Git Bash).
#
#     ./start.sh              first run: creates the venv, installs everything
#     ./start.sh --skip-setup subsequent runs: just launch both servers
#
# Opens the API on :8000 and the dashboard on :5173.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
SKIP_SETUP=0
[[ "${1:-}" == "--skip-setup" ]] && SKIP_SETUP=1

step()  { printf '\n\033[36m==> %s\033[0m\n' "$1"; }
fatal() { printf '\033[31m%s\033[0m\n' "$1" >&2; exit 1; }

command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1 \
  || fatal "Missing Python. Install 3.11+ from https://python.org"
command -v npm >/dev/null 2>&1 \
  || fatal "Missing npm. Install Node.js 18+ from https://nodejs.org"

PYTHON="$(command -v python3 || command -v python)"

# Windows Git Bash puts the venv binaries in Scripts/, POSIX in bin/.
if [[ -d "$BACKEND/.venv/Scripts" ]]; then
  VENV_BIN="$BACKEND/.venv/Scripts"
else
  VENV_BIN="$BACKEND/.venv/bin"
fi

if [[ $SKIP_SETUP -eq 0 ]]; then
  step "Creating the Python virtual environment"
  if [[ ! -d "$BACKEND/.venv" ]]; then
    "$PYTHON" -m venv "$BACKEND/.venv"
    [[ -d "$BACKEND/.venv/Scripts" ]] && VENV_BIN="$BACKEND/.venv/Scripts" || VENV_BIN="$BACKEND/.venv/bin"
  else
    echo "   already present, reusing it"
  fi

  VENV_PY="$VENV_BIN/python"
  [[ -x "$VENV_PY" ]] || VENV_PY="$VENV_BIN/python.exe"

  step "Installing backend dependencies"
  # The pinned set targets Python 3.11; newer interpreters have no wheels for
  # those exact versions, so fall back to the floors file.
  VERSION="$("$VENV_PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  if [[ "$VERSION" == "3.11" ]]; then
    REQS="$BACKEND/requirements.txt"
  else
    echo "   Python $VERSION detected -- using requirements-latest.txt"
    REQS="$BACKEND/requirements-latest.txt"
  fi
  "$VENV_PY" -m pip install --quiet --upgrade pip
  "$VENV_PY" -m pip install --quiet -r "$REQS"
  "$VENV_PY" -m pip install --quiet httpx

  step "Installing frontend dependencies"
  (cd "$FRONTEND" && npm install --no-audit --no-fund)
fi

VENV_PY="$VENV_BIN/python"
[[ -x "$VENV_PY" ]] || VENV_PY="$VENV_BIN/python.exe"
[[ -x "$VENV_PY" ]] || fatal "No virtual environment found. Run ./start.sh without --skip-setup first."

cleanup() {
  echo ""
  echo "Shutting down…"
  kill "${BACKEND_PID:-}" "${FRONTEND_PID:-}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

step "Starting the FastAPI backend on http://localhost:8000"
(cd "$BACKEND" && "$VENV_PY" -m uvicorn app.main:app --reload --port 8000) &
BACKEND_PID=$!

sleep 3

step "Starting the Vite dashboard on http://localhost:5173"
(cd "$FRONTEND" && npm run dev) &
FRONTEND_PID=$!

sleep 4
printf '\n\033[32mDashboard  http://localhost:5173\033[0m\n'
printf '\033[32mAPI docs   http://localhost:8000/docs\033[0m\n\n'
printf '\033[90mPress Ctrl+C to stop both servers.\033[0m\n'

wait
