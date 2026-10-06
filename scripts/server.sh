#!/bin/sh
# clientall server control from the developer PC. Settings: scripts/server.env (copy server.env.example; never committed).
#   sh scripts/server.sh setup                 one-time server setup (root SSH)
#   sh scripts/server.sh deploy test|prod      tests -> build Next.js here -> upload -> migrate -> switch -> health check
#   sh scripts/server.sh rollback test|prod    back to the previous release
#   sh scripts/server.sh status|logs test|prod
#   sh scripts/server.sh cli test|prod <args>  backend CLI on the server, e.g. cli prod tenant:list
# SKIP_TESTS=1 skips the local test run (not recommended for prod).
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cmd=${1:-}; inst=${2:-}
if [ "$cmd" != package ]; then
  CONF="$ROOT/scripts/server.env"
  [ -f "$CONF" ] || { echo "create $CONF from scripts/server.env.example"; exit 1; }
  . "$CONF"
  : "${SERVER_HOST:?set SERVER_HOST in server.env}"
  SSH_OPTS="-o StrictHostKeyChecking=accept-new -o IdentitiesOnly=yes ${SSH_KEY:+-i $SSH_KEY}"
  DEPLOY="clientus@$SERVER_HOST"
fi

# a release folder: API code, the prebuilt Next.js standalone server, deploy scripts, studio configs
package() {
  out=$1; mkdir -p "$out"
  rsync -a --exclude .venv --exclude data --exclude tests --exclude __pycache__ --exclude .pytest_cache --exclude 'requirements-dev.txt' "$ROOT/api/" "$out/api/"
  mkdir -p "$out/web/.next"
  cp -a "$ROOT/web/.next/standalone/." "$out/web/"
  cp -a "$ROOT/web/.next/static" "$out/web/.next/static"
  [ -d "$ROOT/web/public" ] && cp -a "$ROOT/web/public/." "$out/web/public/"
  rsync -a --exclude selfhosted "$ROOT/deploy/" "$out/deploy/"
  [ -d "$ROOT/tenants" ] && rsync -a "$ROOT/tenants/" "$out/tenants/"
  echo "$2" > "$out/VERSION"
}

need_inst() { case "$inst" in prod|test) ;; *) echo "usage: $0 $cmd test|prod"; exit 1;; esac; }

case "$cmd" in
setup)
  : "${PROD_DOMAIN:?}" "${TEST_DOMAIN:?}" "${ACME_EMAIL:?}"
  KEY_FILE=${SSH_KEY:-$HOME/.ssh/id_ed25519}
  [ -f "$KEY_FILE.pub" ] || { echo "no public key $KEY_FILE.pub (ssh-keygen -t ed25519)"; exit 1; }
  rsync -az -e "ssh $SSH_OPTS" "$ROOT/deploy/platform/" "${ROOT_USER:-root}@$SERVER_HOST:/tmp/clientus-setup/"
  ssh $SSH_OPTS "${ROOT_USER:-root}@$SERVER_HOST" \
    "PROD_DOMAIN='$PROD_DOMAIN' TEST_DOMAIN='$TEST_DOMAIN' ACME_EMAIL='$ACME_EMAIL' DEPLOY_KEY='$(cat "$KEY_FILE.pub")' sh /tmp/clientus-setup/server-setup.sh"
  ;;

deploy)
  need_inst
  VERSION="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo nogit)$(git -C "$ROOT" diff --quiet 2>/dev/null || echo -dirty) $(date '+%Y-%m-%d %H:%M')"
  if [ "$inst" = prod ]; then
    case "$VERSION" in *-dirty*) echo "uncommitted changes: commit before deploying to prod"; exit 1;; esac
    printf "deploy %s to PROD? type yes: " "$VERSION"; read -r ok; [ "$ok" = yes ] || exit 1
  fi
  if [ "${SKIP_TESTS:-}" != 1 ]; then
    echo "== tests"
    (cd "$ROOT/api" && .venv/bin/python -m pytest -q -x >/dev/null) || { echo "backend tests failed"; exit 1; }
    (cd "$ROOT/web" && npx tsc --noEmit -p . && npx vitest run >/dev/null) || { echo "web checks failed"; exit 1; }
  fi
  echo "== build (Next.js standalone)"
  (cd "$ROOT/web" && pnpm build >/dev/null)
  STAGE=$(mktemp -d); trap 'rm -rf "$STAGE"' EXIT
  package "$STAGE" "$VERSION"
  REL="/srv/clientus/$inst/releases/$(date +%Y%m%d-%H%M%S)"
  echo "== upload $(du -sh "$STAGE" | cut -f1) -> $inst"
  rsync -az --delete -e "ssh $SSH_OPTS" --link-dest="/srv/clientus/$inst/current/" "$STAGE/" "$DEPLOY:$REL/"
  echo "== activate"
  ssh $SSH_OPTS "$DEPLOY" "sh $REL/deploy/platform/activate.sh $inst $REL"
  ;;

rollback)
  need_inst
  ssh $SSH_OPTS "$DEPLOY" "sh /srv/clientus/$inst/current/deploy/platform/activate.sh $inst --rollback"
  ;;

status)
  need_inst
  ssh $SSH_OPTS "$DEPLOY" "cat /srv/clientus/$inst/current/VERSION; systemctl is-active clientus-api@$inst clientus-web@$inst clientus-worker@$inst"
  ;;

logs)
  need_inst
  ssh $SSH_OPTS "$DEPLOY" "journalctl -u clientus-api@$inst -u clientus-web@$inst -u clientus-worker@$inst -n 100 --no-pager"
  ;;

cli)
  need_inst; shift 2
  ssh -t $SSH_OPTS "$DEPLOY" "cd /srv/clientus/$inst/current/api && set -a && . /srv/clientus/$inst/.env && set +a && /srv/clientus/$inst/venv/bin/python -m app.cli $*"
  ;;

package)  # local only: sh scripts/server.sh package <empty dir> (uses the current web build)
  [ -n "$inst" ] || { echo "usage: $0 package <dir>"; exit 1; }
  package "$inst" "local $(date '+%Y-%m-%d %H:%M')"
  ;;

*)
  sed -n '2,9p' "$0"; exit 1
  ;;
esac
