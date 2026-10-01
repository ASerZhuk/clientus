#!/bin/sh
# Consistent SQLite backup + photos. Run daily from cron:  15 3 * * * /srv/clientus/deploy/backup.sh
set -eu
DATA=${DATA_DIR:-/srv/clientus/data}
OUT=${BACKUP_DIR:-/srv/backups/clientus}
STAMP=$(date +%Y%m%d-%H%M)
mkdir -p "$OUT"
# .backup takes a snapshot that is safe while the API is writing (WAL)
sqlite3 "$DATA/app.db" ".backup '$OUT/app-$STAMP.db'"
tar -C "$DATA" -czf "$OUT/media-$STAMP.tar.gz" media
# keep 14 days
find "$OUT" -type f -mtime +14 -delete
echo "backup ok: $OUT/app-$STAMP.db"
