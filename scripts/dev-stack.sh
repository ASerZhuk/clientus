#!/bin/sh
# Local dev stack in the background: API :8010, worker, web :3000 (production build). Stop with: sh scripts/dev-stack.sh stop
ROOT=$(cd "$(dirname "$0")/.." && pwd)
LOG=${DEV_LOG_DIR:-/tmp}
stop() {
  for port in 3000 8010 3443 3080; do for pid in $(ss -ltnp 2>/dev/null | grep ":$port " | grep -o 'pid=[0-9]*' | cut -d= -f2); do kill -9 "$pid" 2>/dev/null; done; done
  [ -f "$LOG/clientus-worker.pid" ] && kill "$(cat "$LOG/clientus-worker.pid")" 2>/dev/null; rm -f "$LOG/clientus-worker.pid"
}
stop
[ "$1" = "stop" ] && exit 0
# the machine's LAN address: the site is reachable from phones in the same Wi-Fi at http://$LAN_IP:3000
# every address of this machine (LAN, VPN...) serves the platform; set LAN_IPS to limit it
LAN_IPS=${LAN_IPS:-$(hostname -I 2>/dev/null)}
LAN_IP=$(echo "$LAN_IPS" | awk '{print $1}')
export PLATFORM_HOSTS="localhost,127.0.0.1$(for ip in $LAN_IPS; do printf ',%s' "$ip"; done)"
export PUBLIC_ORIGINS="http://localhost:3000,https://localhost:3443$(for ip in $LAN_IPS; do printf ',http://%s:3000,https://%s:3443' "$ip" "$ip"; done)"
cd "$ROOT/api" && nohup .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8010 > "$LOG/clientus-api.log" 2>&1 &
cd "$ROOT/api" && nohup .venv/bin/python -m app.worker > "$LOG/clientus-worker.log" 2>&1 &
echo $! > "$LOG/clientus-worker.pid"
cd "$ROOT/web" && INTERNAL_API_URL=http://127.0.0.1:8010 HOSTNAME=0.0.0.0 nohup sh scripts/serve.sh 3000 > "$LOG/clientus-web.log" 2>&1 &
# HTTPS for phones in the same Wi-Fi: install, service worker and push need a secure origin, plain http://IP is not one.
# Caddy issues certificates from its own local CA; a phone trusts them after installing the CA from http://IP:3080/
if command -v caddy >/dev/null 2>&1; then
  TLS="$ROOT/.dev-tls"; mkdir -p "$TLS"
  SITES="https://localhost:3443$(for ip in $LAN_IPS; do printf ', https://%s:3443' "$ip"; done)"
  cat > "$TLS/Caddyfile" <<CADDY
{
	admin off
	storage file_system "$TLS/storage"
	skip_install_trust
	local_certs
	auto_https disable_redirects
}
$SITES {
	tls internal
	reverse_proxy 127.0.0.1:3000
}
http://:3080 {
	root * "$TLS/storage/pki/authorities/local"
	rewrite / /root.crt
	header Content-Type application/x-x509-ca-cert
	header Content-Disposition "attachment; filename=clientus-dev-ca.crt"
	file_server
}
CADDY
  nohup caddy run --config "$TLS/Caddyfile" --adapter caddyfile > "$LOG/clientus-caddy.log" 2>&1 &
fi
sleep 6
ss -ltn | grep -E ":(8010|3000|3443) "
for ip in $LAN_IPS; do case $ip in 172.1[6-9].*|172.2[0-9].*|172.3[01].*) ;; *) echo "open: http://$ip:3000/  https (install, push): https://$ip:3443/  CA for the phone: http://$ip:3080/";; esac; done
