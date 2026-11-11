#!/usr/bin/env bash
# Start the mock Andakia Voice API (port 9000) and the phone line (port 8080),
# run one simulated call, then stop both. Usage: ./scripts/run_local.sh [wo|fr]
set -euo pipefail
cd "$(dirname "$0")/.."

export ANDAKIA_API_URL="http://localhost:9000"
export ANDAKIA_API_KEY="${ANDAKIA_API_KEY:-demo-key-not-real}"
export PUBLIC_BASE_URL="http://localhost:8080"
export HUMAN_TRANSFER_TARGET="${HUMAN_TRANSFER_TARGET:-sip:health-desk@pbx.example.com}"
export CALL_LOG_PATH="${CALL_LOG_PATH:-data/calls.sqlite3}"
export LOG_LEVEL=WARNING

python -m uvicorn mock_api.server:app --host localhost --port 9000 --log-level warning &
MOCK_PID=$!
python -m ligne_rose &
LINE_PID=$!
trap 'kill $MOCK_PID $LINE_PID 2>/dev/null || true' EXIT

for _ in $(seq 1 50); do
  if curl -fs http://localhost:8080/health >/dev/null && curl -fs http://localhost:9000/health >/dev/null; then
    break
  fi
  sleep 0.2
done

python scripts/simulate_call.py --lang "${1:-wo}"
