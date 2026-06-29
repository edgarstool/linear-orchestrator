#!/usr/bin/env bash
# Switch ~/.cloudflared/config.yml on the Windows host:
#   webhooks.edgars.tools → localhost:8645  (Dashboard edgar-local-01-tunnel; Windows native)
# Run from WSL. Edits the Windows path via /mnt/c.
set -e
WIN_USER="${WIN_USER:-EdgarsTool}"
CFG="/mnt/c/Users/$WIN_USER/.cloudflared/config.yml"
if [ ! -f "$CFG" ]; then
  echo "config not found: $CFG"
  exit 1
fi
WSL_IP=$(hostname -I | awk '{print $1}')
cp -f "$CFG" "$CFG.bak.orchestrator-switch.$(date +%Y%m%d%H%M%S)"
python3 - "$CFG" "$WSL_IP" <<'PY'
import re, sys
cfg = sys.argv[1]; ip = sys.argv[2]
src = open(cfg, encoding="utf-8").read()
new = re.sub(r"(- hostname: webhook\.whoasked\.vip\s*\n\s*service: )http://[^\s]+", rf"\1http://{ip}:8645", src)
open(cfg, "w", encoding="utf-8").write(new)
print("rewrote", cfg, "→", ip + ":8645")
PY
echo "restart cloudflared on Windows:"
echo "  taskkill /IM cloudflared.exe /F && start /B cloudflared tunnel run home-tunnel"
