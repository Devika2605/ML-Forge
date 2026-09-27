#!/usr/bin/env bash
# Runs the full backend test suite: scoring unit tests (no server needed)
# and the full-event API integration test (starts a temporary server).
set -e
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
  echo "No venv found. Run ./setup.sh first."
  exit 1
fi
PY="venv/bin/python3"

echo "== Scoring unit tests =="
$PY tests/test_scoring_unit.py

echo
echo "== Starting temporary server for integration test =="
rm -f app/mlforge_test.db
MLFORGE_DATABASE_URL="sqlite:///$(pwd)/app/mlforge_test.db" $PY -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/mlforge_test_server.log 2>&1 &
SERVER_PID=$!
sleep 3

echo "== Full event integration test =="
$PY tests/test_full_event.py
RESULT=$?

kill $SERVER_PID 2>/dev/null || true
rm -f app/mlforge_test.db

exit $RESULT
