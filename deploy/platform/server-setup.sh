#!/bin/sh
# One-time setup of a fresh Ubuntu 24.04 VPS for the Clientus platform. Run as root (scripts/server.sh setup does it):
#   PROD_DOMAIN=clientus.ru TEST_DOMAIN=test.clientus.ru ACME_EMAIL=you@mail.ru DEPLOY_KEY="ssh-ed25519 ..." sh server-setup.sh
# Safe to run again: existing .env files, databases and keys are kept.
set -eu
: "${PROD_DOMAIN:?}" "${TEST_DOMAIN:?}" "${ACME_EMAIL:?}" "${DEPLOY_KEY:?}"
HERE=$(cd "$(dirname "$0")" && pwd)
BASE=/srv/clientus

echo "== packages"
export DEBIAN_FRONTEND=noninteractive
rm -f /etc/apt/sources.list.d/caddy-stable.list   # Caddy comes from its release binary below
apt-get update -q
apt-get install -y -q curl ca-certificates gnupg rsync sqlite3 ufw debian-keyring debian-archive-keyring apt-transport-https
# Node.js 22 (runs the prebuilt Next.js server; nothing is built here)
if ! command -v node >/dev/null || ! node --version | grep -q '^v22'; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y -q nodejs
fi
# Caddy (automatic HTTPS): the official release binary + the official systemd unit
# (its apt repository is not used: its signing key can expire and then breaks every apt update)
if ! command -v caddy >/dev/null; then
  ARCH=$(dpkg --print-architecture)
  V=$(curl -fsSL https://api.github.com/repos/caddyserver/caddy/releases/latest | sed -n 's/.*"tag_name": *"v\([0-9.]*\)".*/\1/p')
  curl -fsSL "https://github.com/caddyserver/caddy/releases/download/v$V/caddy_${V}_linux_$ARCH.tar.gz" | tar -xz -C /usr/bin caddy
  getent group caddy >/dev/null || groupadd --system caddy
  id caddy >/dev/null 2>&1 || useradd --system --gid caddy --create-home --home-dir /var/lib/caddy --shell /usr/sbin/nologin caddy
  mkdir -p /etc/caddy
  cat > /etc/systemd/system/caddy.service <<'UNIT'
[Unit]
Description=Caddy
After=network.target network-online.target
Requires=network-online.target

[Service]
Type=notify
User=caddy
Group=caddy
ExecStart=/usr/bin/caddy run --environ --config /etc/caddy/Caddyfile
ExecReload=/usr/bin/caddy reload --config /etc/caddy/Caddyfile --force
TimeoutStopSec=5s
LimitNOFILE=1048576
PrivateTmp=true
ProtectSystem=full
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_BIND_SERVICE

[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
fi

echo "== user, folders, deploy key"
id clientus >/dev/null 2>&1 || useradd -r -m -d "$BASE" -s /bin/bash clientus
install -d -o clientus -g clientus -m 700 "$BASE/.ssh"
grep -qxF "$DEPLOY_KEY" "$BASE/.ssh/authorized_keys" 2>/dev/null || echo "$DEPLOY_KEY" >> "$BASE/.ssh/authorized_keys"
chown clientus:clientus "$BASE/.ssh/authorized_keys"; chmod 600 "$BASE/.ssh/authorized_keys"
usermod -aG systemd-journal clientus   # read its own service logs (server.sh logs)
# uv installs the exact Python version the tests ran on (api/.python-version)
[ -x "$BASE/.local/bin/uv" ] || sudo -u clientus sh -c 'curl -LsSf https://astral.sh/uv/install.sh | sh' >/dev/null
# the deploy user may restart only its own services
cat > /etc/sudoers.d/clientus <<'SUDO'
clientus ALL=(root) NOPASSWD: /usr/bin/systemctl restart clientus-api@prod, /usr/bin/systemctl restart clientus-web@prod, /usr/bin/systemctl restart clientus-worker@prod, /usr/bin/systemctl restart clientus-api@test, /usr/bin/systemctl restart clientus-web@test, /usr/bin/systemctl restart clientus-worker@test
SUDO
chmod 440 /etc/sudoers.d/clientus

IP=$(curl -fsS4 https://ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
instance() { # name api_port web_port domain
  dir="$BASE/$1"
  install -d -o clientus -g clientus "$dir" "$dir/releases" "$dir/data" "$dir/backups"
  if [ ! -f "$dir/.env" ]; then
    cat > "$dir/.env" <<ENV
DATA_DIR=$dir/data
SECRET_KEY=$(openssl rand -hex 32)
INTERNAL_TOKEN=$(openssl rand -hex 24)
COOKIE_SECURE=true
PUBLIC_ORIGINS=https://$4
PLATFORM_HOSTS=$4,localhost,127.0.0.1
PLATFORM_NAME=Clientus
PLATFORM_URL=https://$PROD_DOMAIN
PLATFORM_IPS=$IP
ADMIN_ENABLED=true
TRIAL_DAYS=0
API_PORT=$2
PORT=$3
INTERNAL_API_URL=http://127.0.0.1:$2
VAPID_PUBLIC_KEY=
VAPID_PRIVATE_KEY_PATH=$dir/data/vapid_private.pem
VAPID_SUBJECT=mailto:$ACME_EMAIL
VSELLM_BASE_URL=https://api.vsellm.ru/v1
VSELLM_TOKEN=
VSELLM_MODEL=openai/gpt-5.4-nano
ENV
    chown clientus:clientus "$dir/.env"; chmod 600 "$dir/.env"
    echo "   $1: new .env with fresh secrets ($dir/.env)"
  fi
}
instance prod 8000 3000 "$PROD_DOMAIN"
instance test 8001 3001 "$TEST_DOMAIN"

echo "== services"
cp "$HERE"/clientus-api@.service "$HERE"/clientus-web@.service "$HERE"/clientus-worker@.service /etc/systemd/system/
systemctl daemon-reload
for i in prod test; do systemctl enable clientus-api@$i clientus-web@$i clientus-worker@$i >/dev/null 2>&1; done

echo "== Caddy"
sed -e "s/@PROD_DOMAIN@/$PROD_DOMAIN/g" -e "s/@TEST_DOMAIN@/$TEST_DOMAIN/g" -e "s/@ACME_EMAIL@/$ACME_EMAIL/g" "$HERE/Caddyfile.tmpl" > /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1 || { caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile; exit 1; }
systemctl enable caddy >/dev/null 2>&1
systemctl reload caddy 2>/dev/null || systemctl restart caddy

echo "== firewall, swap, backups"
ufw allow OpenSSH >/dev/null; ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; ufw --force enable >/dev/null
if [ ! -f /swapfile ] && [ "$(awk '/MemTotal/ {print $2}' /proc/meminfo)" -lt 3500000 ]; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
( { crontab -u clientus -l 2>/dev/null || true; } | grep -v backup.sh || true
  echo "15 3 * * * DATA_DIR=$BASE/prod/data BACKUP_DIR=$BASE/prod/backups $BASE/prod/current/deploy/backup.sh >/dev/null 2>&1" ) | crontab -u clientus -

echo "done. Next: from your PC run  sh scripts/server.sh deploy test"
