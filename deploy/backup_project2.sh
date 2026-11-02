#!/usr/bin/env bash
set -euo pipefail

ENV_FILE=${ENV_FILE:-/opt/project2/shared/env/familylearning.env}
BACKUP_DIR=${BACKUP_DIR:-/opt/project2/backups/familylearning-daily}
RETENTION_DAYS=${RETENTION_DAYS:-14}
RELEASE_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
PYTHON="$RELEASE_DIR/backend/.venv/bin/python"

set -a
source "$ENV_FILE"
set +a

eval "$("$PYTHON" - <<'PY'
import os
import shlex
from sqlalchemy.engine import make_url

url = make_url(os.environ["FLA_DATABASE_URL"])
for key, value in {
    "DB_HOST": url.host or "127.0.0.1",
    "DB_PORT": str(url.port or 3306),
    "DB_USER": url.username or "",
    "DB_PASSWORD": url.password or "",
    "DB_NAME": url.database or "",
}.items():
    print(f"{key}={shlex.quote(value)}")
PY
)"

test -n "$DB_USER"
test -n "$DB_NAME"
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
STAMP=$(date +%Y%m%d-%H%M%S)
DUMP_TMP="$BACKUP_DIR/english_forest-$STAMP.sql.gz.tmp"
UPLOADS_TMP="$BACKUP_DIR/uploads-$STAMP.tar.gz.tmp"
DUMP="$BACKUP_DIR/english_forest-$STAMP.sql.gz"
UPLOADS="$BACKUP_DIR/uploads-$STAMP.tar.gz"

cleanup() {
  trap - EXIT
  if [[ ! -s "$DUMP" ]]; then
    find "$BACKUP_DIR" -maxdepth 1 -name "english_forest-$STAMP.sql.gz.tmp" -delete
  fi
  if [[ ! -s "$UPLOADS" ]]; then
    find "$BACKUP_DIR" -maxdepth 1 -name "uploads-$STAMP.tar.gz.tmp" -delete
  fi
}
trap cleanup EXIT

export MYSQL_PWD="$DB_PASSWORD"
mysqldump \
  --host="$DB_HOST" --port="$DB_PORT" --user="$DB_USER" \
  --single-transaction --quick --skip-comments --no-tablespaces \
  --default-character-set=utf8mb4 "$DB_NAME" | gzip -9 >"$DUMP_TMP"
gzip -t "$DUMP_TMP"
mv "$DUMP_TMP" "$DUMP"

tar -czf "$UPLOADS_TMP" -C /opt/project2/shared familylearning_uploads
gzip -t "$UPLOADS_TMP"
mv "$UPLOADS_TMP" "$UPLOADS"

(
  cd "$BACKUP_DIR"
  sha256sum "$(basename "$DUMP")" "$(basename "$UPLOADS")" >"SHA256SUMS-$STAMP"
)
find "$BACKUP_DIR" -maxdepth 1 -type f -mtime "+$RETENTION_DAYS" -delete
printf 'backup_completed=%s\n' "$STAMP"
