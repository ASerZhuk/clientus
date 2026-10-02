#!/bin/sh
# Runs on the server as the clientus user (scripts/server.sh calls it): activate an uploaded release.
#   sh activate.sh <prod|test> <release-dir>        sh activate.sh <prod|test> --rollback
set -eu
INST=$1
BASE=${CLIENTUS_BASE:-/srv/clientus}/$INST
UV=${UV:-/srv/clientus/.local/bin/uv}
cd "$BASE"
set -a; . "$BASE/.env"; set +a

restart() { for s in api worker web; do sudo systemctl restart "clientus-$s@$INST"; done; }
healthy() {
  i=0
  while [ $i -lt 20 ]; do
    if curl -fsS "http://127.0.0.1:$API_PORT/api/health" >/dev/null 2>&1 && curl -fsS -o /dev/null "http://127.0.0.1:$PORT/api/health" 2>/dev/null; then return 0; fi
    i=$((i + 1)); sleep 1
  done
  return 1
}

if [ "$2" = "--rollback" ]; then
  cur="releases/$(basename "$(readlink -f current)")"
  prev=$(ls -1d releases/*/ | sed 's#/$##' | sort | awk -v cur="$cur" '$0 == cur { print last; exit } { last = $0 }')
  [ -n "$prev" ] || { echo "no release before $cur"; exit 1; }
  ln -sfn "$BASE/$prev" current.new && mv -T current.new current
  restart
  healthy && echo "rolled back to $(basename "$prev")" || { echo "rolled back, but health check FAILED"; exit 1; }
  exit 0
fi

NEW=$2
OLD=$(readlink -f current 2>/dev/null || true)

# 1. Python dependencies: the exact Python of api/.python-version, reinstalled only when requirements change
REQ_HASH=$(cat "$NEW/api/requirements.txt" "$NEW/api/.python-version" | sha256sum | cut -c1-16)
if [ ! -x venv/bin/python ] || [ "$(cat venv/.req 2>/dev/null)" != "$REQ_HASH" ]; then
  echo "== python $(cat "$NEW/api/.python-version") + requirements"
  rm -rf venv.new
  "$UV" venv --quiet --python "$(cat "$NEW/api/.python-version")" venv.new
  VIRTUAL_ENV="$BASE/venv.new" "$UV" pip install --quiet -r "$NEW/api/requirements.txt"
  echo "$REQ_HASH" > venv.new/.req
  rm -rf venv.old; [ -d venv ] && mv venv venv.old; mv venv.new venv
fi

# 2. push keys on the first deploy of an instance
if [ ! -f data/vapid_private.pem ]; then
  pub=$(cd "$NEW/api" && "$BASE/venv/bin/python" -m app.cli vapid:generate --out "$BASE/data/vapid_private.pem" | sed -n 's/^VAPID_PUBLIC_KEY=//p')
  sed -i "s|^VAPID_PUBLIC_KEY=.*|VAPID_PUBLIC_KEY=$pub|" "$BASE/.env"
  export VAPID_PUBLIC_KEY="$pub"
  echo "== push keys created"
fi

# 3. database: snapshot, then migrations
if [ -f data/app.db ]; then sqlite3 data/app.db ".backup 'backups/pre-deploy-$(date +%Y%m%d-%H%M%S).db'"; fi
(cd "$NEW/api" && "$BASE/venv/bin/python" -m alembic upgrade head)

# 4. switch atomically and restart
ln -sfn "$NEW" current.new && mv -T current.new current
restart
if healthy; then
  echo "== live: $(cat "$NEW/VERSION")"
else
  echo "!! health check failed"
  if [ -n "$OLD" ]; then
    ln -sfn "$OLD" current.new && mv -T current.new current
    restart
    echo "!! rolled back to $(basename "$OLD") (the database stays migrated; a pre-deploy copy is in backups/)"
  fi
  exit 1
fi

# 5. keep the last 5 releases and 10 pre-deploy database copies
ls -1d releases/*/ | sort | head -n -5 | xargs -r rm -rf
ls -1 backups/pre-deploy-*.db 2>/dev/null | sort | head -n -10 | xargs -r rm -f
