#!/usr/bin/env bash
# Install linear-orchestrator as a systemd unit so it survives WSL restart.
# Run this ONCE after setup. Needs sudo (will prompt for password).
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_NAME="$(whoami)"
TMPL="$HERE/systemd/linear-orchestrator.service.tmpl"
SVC=/etc/systemd/system/linear-orchestrator.service

if ! command -v systemctl >/dev/null 2>&1; then
  echo "systemctl not available. Enable WSL systemd:"
  echo "  echo -e '[boot]\\nsystemd=true' | sudo tee -a /etc/wsl.conf"
  echo "  (in Windows PowerShell) wsl --shutdown"
  exit 1
fi
if ! [ -d /etc/systemd/system ]; then
  echo "/etc/systemd/system missing — systemd not active. Enable as above."
  exit 1
fi

echo "[1/3] writing unit to $SVC (sudo)"
sed "s|__HERE__|$HERE|g; s|__USER__|$USER_NAME|g" "$TMPL" | sudo tee "$SVC" >/dev/null

echo "[2/3] daemon-reload + enable + start"
sudo systemctl daemon-reload
sudo systemctl enable --now linear-orchestrator

echo "[3/3] status"
sudo systemctl --no-pager status linear-orchestrator | head -15

echo
echo "DONE. Useful follow-ups:"
echo "  sudo journalctl -u linear-orchestrator -f       # live log"
echo "  sudo systemctl restart linear-orchestrator     # bounce"
echo "  sudo systemctl disable --now linear-orchestrator  # uninstall"
