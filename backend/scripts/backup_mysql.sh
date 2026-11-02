#!/usr/bin/env bash
set -euo pipefail

: "${MYSQL_HOST:=127.0.0.1}"
: "${MYSQL_PORT:=3306}"
: "${MYSQL_USER:?MYSQL_USER is required}"
: "${MYSQL_PASSWORD:?MYSQL_PASSWORD is required}"
: "${BUSINESS_DB:=familylearning}"
: "${CHECKPOINT_DB:=familylearning_checkpoints}"
: "${BACKUP_DIR:=./backups}"

mkdir -p "$BACKUP_DIR"
stamp="$(date +%Y%m%d-%H%M%S)"
export MYSQL_PWD="$MYSQL_PASSWORD"

mysqldump --host="$MYSQL_HOST" --port="$MYSQL_PORT" --user="$MYSQL_USER" \
  --single-transaction --skip-comments --no-tablespaces "$BUSINESS_DB" \
  > "$BACKUP_DIR/business-$stamp.sql"
mysqldump --host="$MYSQL_HOST" --port="$MYSQL_PORT" --user="$MYSQL_USER" \
  --single-transaction --skip-comments --no-tablespaces "$CHECKPOINT_DB" \
  > "$BACKUP_DIR/checkpoints-$stamp.sql"

echo "Backup completed: $BACKUP_DIR/business-$stamp.sql and $BACKUP_DIR/checkpoints-$stamp.sql"
