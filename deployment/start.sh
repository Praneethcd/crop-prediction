#!/bin/sh
set -eu
if [ "$(id -u)" = "0" ]; then
  mkdir -p /data/instance
  chown -R appuser:appuser /data
  exec gosu appuser sh deployment/start.sh
fi
mkdir -p "${AGRIPREDICT_INSTANCE_PATH:-/data/instance}"
python -m services.monitor --interval "${CROP_MONITOR_INTERVAL_SECONDS:-900}" &
monitor_pid=$!
trap 'kill "$monitor_pid" 2>/dev/null || true' EXIT INT TERM
# One worker preserves the small SQLite deployment; gthread permits concurrent image/API requests.
gunicorn --bind "0.0.0.0:${PORT:-8000}" --workers 1 --threads 4 --timeout 120 app:app &
web_pid=$!
trap 'kill "$web_pid" "$monitor_pid" 2>/dev/null || true' EXIT INT TERM
wait "$web_pid"
