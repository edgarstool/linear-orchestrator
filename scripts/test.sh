#!/usr/bin/env bash
# End-to-end test: sign a Linear-shaped payload and POST.
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$HOME/.hermes/.env" 2>/dev/null || true
[ -f "$HERE/.env" ] && . "$HERE/.env" || true
: "${LINEAR_WEBHOOK_SECRET:?LINEAR_WEBHOOK_SECRET not set}"
PORT="${ORCHESTRATOR_PORT:-8645}"
URL="${1:-http://127.0.0.1:$PORT/webhooks/linear}"

TS=$(($(date +%s) * 1000))
BODY="{\"action\":\"create\",\"type\":\"Comment\",\"data\":{\"id\":\"c-test\",\"body\":\"@hermes please ack\",\"issueId\":\"i-test\",\"issue\":{\"id\":\"i-test\",\"identifier\":\"TEST-1\",\"title\":\"orchestrator e2e\"}},\"webhookTimestamp\":$TS}"
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$LINEAR_WEBHOOK_SECRET" -hex | awk '{print $NF}')
echo "POST $URL"
echo "body: $BODY"
curl -s -i -X POST "$URL" \
  -H "Content-Type: application/json" \
  -H "Linear-Signature: $SIG" \
  --data "$BODY"
echo
# Oz smoke test comment
