#!/bin/sh
# One-shot installer for a customer's own server (Ubuntu 22.04+/Debian 12+). Run as root from the unpacked package:
#   tar xzf @SLUG@-package.tar.gz && cd @SLUG@-package && sudo sh install.sh
# Before running: the domain @DOMAIN@ must have an A record pointing at this server (ports 80 and 443 open).
set -eu

DOMAIN="@DOMAIN@"
ROOT=/srv/clientus
SRC=$(cd "$(dirname "$0")" && pwd)

[ "$(id -u)" = 0 ] || { echo "Run as root: sudo sh install.sh"; exit 1; }
echo "==> installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip sqlite3 curl ca-certificates gnupg debian-keyring debian-archive-keyring apt-transport-https

if ! command -v node >/dev/null 2>&1 || [ "$(node -p 'process.versions.node.split(".")[0]')" -lt 22 ]; then
  echo "==> installing Node.js 22"
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y nodejs
fi
command -v pnpm >/dev/null 2>&1 || npm install -g pnpm@11.1.2

if ! command -v caddy >/dev/null 2>&1; then
  echo "==> installing Caddy (automatic HTTPS)"
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y && apt-get install -y caddy
fi

echo "==> creating the service user and copying the application to $ROOT"
id clientus >/dev/null 2>&1 || useradd -r -m -d "$ROOT" -s /usr/sbin/nologin clientus
mkdir -p "$ROOT"
cp -a "$SRC"/api "$SRC"/web "$SRC"/deploy "$SRC"/scripts "$SRC"/tenants "$SRC"/package.json "$ROOT"/
[ -d "$ROOT/data" ] || cp -a "$SRC"/data "$ROOT"/data           # never overwrite existing data on a re-run
[ -f "$ROOT/.env" ] || { cp "$SRC"/.env "$ROOT"/.env; chmod 600 "$ROOT/.env"; }
chown -R clientus:clientus "$ROOT"

echo "==> backend (Python)"
sudo -u clientus python3 -m venv "$ROOT/api/.venv"
sudo -u clientus "$ROOT/api/.venv/bin/pip" install --quiet -r "$ROOT/api/requirements.txt"

echo "==> frontend (build takes a few minutes)"
sudo -u clientus sh -c "cd $ROOT/web && pnpm install --frozen-lockfile && pnpm build && cp -a .next/static .next/standalone/.next/static && cp -a public .next/standalone/public"

echo "==> database migrations"
sudo -u clientus sh -c "cd $ROOT/api && set -a && . $ROOT/.env && set +a && .venv/bin/alembic upgrade head"

echo "==> services"
cp "$ROOT"/deploy/clientus-api.service "$ROOT"/deploy/clientus-web.service "$ROOT"/deploy/clientus-worker.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now clientus-api clientus-web clientus-worker

echo "==> HTTPS reverse proxy for $DOMAIN"
cp "$SRC"/Caddyfile /etc/caddy/Caddyfile
systemctl reload caddy || systemctl restart caddy

echo "==> daily backup (03:15) of the database and photos"
( { crontab -u clientus -l 2>/dev/null || true; } | grep -v backup.sh || true; echo "15 3 * * * DATA_DIR=$ROOT/data $ROOT/deploy/backup.sh" ) | crontab -u clientus -

echo
echo "Done. Open https://$DOMAIN/  (the certificate is issued on the first visit; DNS must already point here)."
echo "Owner cabinet: https://$DOMAIN/owner   Logs: journalctl -u clientus-api -u clientus-web -f"
echo "Push notifications need VAPID keys: see README-INSTALL.md, section «Уведомления»."
