#!/usr/bin/env bash
# Snapshot the durable runtime state (sessions + deliveries + webhook payloads).
# Safe to run while the service is running — SQLite online backup, not a file copy.
#
# Cron example (daily 03:15, keep 14 snapshots):
#   15 3 * * * KEEP=14 /home/edgar/linear-orchestrator/scripts/backup-state.sh >> /tmp/lo-backup.log 2>&1
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEEP="${KEEP:-7}"

VENV="${VENV:-$HOME/linear-orchestrator-venv}"
[ -x "$VENV/bin/python" ] || VENV="$HERE/.venv"
PY="$VENV/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

"$PY" -m linear_orchestrator.state_cli backup --keep "$KEEP"
"$PY" -m linear_orchestrator.state_cli verify
