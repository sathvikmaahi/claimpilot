#!/usr/bin/env bash
# Invoke a registered agent via the local API server.
set -euo pipefail

AGENT_ID="${1:?Usage: invoke_agent.sh <agent_id> <message>}"
MESSAGE="${2:?Usage: invoke_agent.sh <agent_id> <message>}"
BASE_URL="${BASE_URL:-http://localhost:8080}"

curl -sS -X POST "${BASE_URL}/agents/${AGENT_ID}/run" \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"${MESSAGE}\", \"user_id\": \"dev-user\"}" | python3 -m json.tool
