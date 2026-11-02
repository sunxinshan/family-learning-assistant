#!/usr/bin/env bash
set -euo pipefail

: "${MYSQL_HOST:=127.0.0.1}"
: "${MYSQL_PORT:=3306}"
: "${MYSQL_USER:?MYSQL_USER is required}"
: "${MYSQL_PASSWORD:?MYSQL_PASSWORD is required}"
: "${BUSINESS_DB:=familylearning}"
: "${CHECKPOINT_DB:=familylearning_checkpoints}"
: "${BUSINESS_BACKUP:?BUSINESS_BACKUP is required}"
: "${CHECKPOINT_BACKUP:?CHECKPOINT_BACKUP is required}"

export MYSQL_PWD="$MYSQL_PASSWORD"
mysql --host="$MYSQL_HOST" --port="$MYSQL_PORT" --user="$MYSQL_USER" "$BUSINESS_DB" < "$BUSINESS_BACKUP"
mysql --host="$MYSQL_HOST" --port="$MYSQL_PORT" --user="$MYSQL_USER" "$CHECKPOINT_DB" < "$CHECKPOINT_BACKUP"
echo "Restore completed into $BUSINESS_DB and $CHECKPOINT_DB"
