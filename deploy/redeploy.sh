#!/usr/bin/env bash
# Redeploys the backend on the VPS: pull latest code, install deps,
# restart the systemd service. Run this from inside caleb-backend/.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

echo "==> Pulling latest code"
git pull

echo "==> Installing dependencies"
source .venv/bin/activate
pip install --quiet -r requirements.txt

echo "==> Reminder: if supabase/schema.sql changed, apply the diff manually"
echo "    in the Supabase SQL editor — this script does not run migrations."

echo "==> Restarting service"
sudo systemctl restart caleb-backend

echo "==> Checking health"
sleep 2
curl -sf http://127.0.0.1:8000/health && echo " OK" || {
    echo "Health check failed — check: sudo journalctl -u caleb-backend -n 50"
    exit 1
}

echo "==> Done"
