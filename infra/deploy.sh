#!/usr/bin/env bash
# Deploy/update Pleiades on the Vultr VM. Run from anywhere as a sudo-capable user:
#   sudo -E /opt/pleiades/infra/deploy.sh
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/pleiades}"
APP_USER="${APP_USER:-pleiades}"
UNITS=(
  pleiades-api.service
  pleiades-ingest-weather.service pleiades-ingest-weather.timer
  pleiades-score.service pleiades-score.timer
  pleiades-ingest-astro.service pleiades-ingest-astro.timer
)
TIMERS=(pleiades-ingest-weather.timer pleiades-score.timer pleiades-ingest-astro.timer)

cd "$APP_DIR"
echo "==> git pull"
sudo -u "$APP_USER" git pull --ff-only

if [[ -f frontend/package.json ]]; then
  echo "==> building frontend"
  (cd frontend && sudo -u "$APP_USER" npm ci && sudo -u "$APP_USER" npm run build)
fi

echo "==> backend dependencies"
cd "$APP_DIR/backend"
if [[ ! -d .venv ]]; then
  sudo -u "$APP_USER" python3 -m venv .venv
fi
sudo -u "$APP_USER" .venv/bin/pip install --quiet --upgrade pip
sudo -u "$APP_USER" .venv/bin/pip install --quiet -r requirements.txt

echo "==> migrations"
sudo -u "$APP_USER" bash -c "set -a; source '$APP_DIR/.env'; set +a; .venv/bin/python -m app.migrate"

echo "==> systemd units"
for unit in "${UNITS[@]}"; do
  install -m 0644 "$APP_DIR/infra/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl enable --now "${TIMERS[@]}"
systemctl enable pleiades-api.service
systemctl restart pleiades-api.service

if [[ -f "$APP_DIR/infra/nginx.conf" && -d /etc/nginx/sites-available ]]; then
  echo "==> nginx"
  if [[ ! -e /etc/nginx/sites-available/pleiades ]]; then
    install -m 0644 "$APP_DIR/infra/nginx.conf" /etc/nginx/sites-available/pleiades
    ln -sf /etc/nginx/sites-available/pleiades /etc/nginx/sites-enabled/pleiades
  fi
  nginx -t && systemctl reload nginx
fi

echo "==> done"
systemctl --no-pager --lines=5 status pleiades-api.service || true
