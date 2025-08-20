#!/bin/sh
# Double-clickable launcher for macOS to run the local web server (POSIX sh)
set -eu

DIR="$(cd "$(dirname "$0")" && pwd)"

alert() {
  msg=$1
  if command -v osascript >/dev/null 2>&1; then
    # Safe quoting for AppleScript: close/open single quotes around the shell-expanded string
    osascript -e 'display dialog '"$msg"' buttons {"OK"} with icon caution' || true
  else
    printf '%s\n' "$msg" >&2
  fi
}

# Check Python 3
if ! command -v python3 >/dev/null 2>&1; then
  alert "Не найден Python 3. Установите Python 3 (например, через Homebrew: brew install python) и запустите снова."
  exit 1
fi

# Optional: check ffmpeg availability (processing requires it)
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  alert "Не найден ffmpeg/ffprobe. Установите: brew install ffmpeg. Приложение запустится, но обработка видео будет недоступна."
fi

# Create venv if missing
if [ ! -d "${DIR}/.venv" ]; then
  echo "Creating virtual environment (.venv)..."
  python3 -m venv "${DIR}/.venv"
fi

# Activate venv
source "${DIR}/.venv/bin/activate"

# Install/update deps
if [ -f "${DIR}/requirements.txt" ]; then
  echo "Installing dependencies..."
  pip install --upgrade pip >/dev/null 2>&1 || true
  pip install -r "${DIR}/requirements.txt"
fi

# Start server in background
echo "Starting VideoCutApp server..."
python3 "${DIR}/app.py" &
APP_PID=$!

cleanup() {
  if kill -0 "$APP_PID" >/dev/null 2>&1; then
    echo "Stopping server (PID $APP_PID)..."
    kill "$APP_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

# Wait for server and open browser
echo "Waiting for server on http://127.0.0.1:5000 ..."
for i in $(seq 1 50); do
  if curl -sSf "http://127.0.0.1:5000" >/dev/null 2>&1; then
    open "http://127.0.0.1:5000" || true
    break
  fi
  sleep 0.2
done

echo "VideoCutApp is running. Оставьте это окно открытым.\nЗакройте окно, чтобы остановить сервер."

# Keep foreground attached to child
wait "$APP_PID"
