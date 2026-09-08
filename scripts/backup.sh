#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$APP_DIR"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
: "${ODOO_DB_NAME:?ODOO_DB_NAME is required}"

mkdir -p backups
docker compose up -d db
docker compose exec -T db pg_isready -U odoo -d postgres
if docker compose exec -T db psql -U odoo -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$ODOO_DB_NAME'" | grep -q 1; then
  file="backups/odoo-${ODOO_DB_NAME}-$(date -u +%Y%m%dT%H%M%SZ).dump.gz"
  docker compose exec -T db pg_dump -U odoo -Fc "$ODOO_DB_NAME" | gzip > "$file"
  find backups -type f -name '*.dump.gz' -mtime +14 -delete
  echo "Backup created: $file"
else
  echo "Database $ODOO_DB_NAME does not exist yet; no backup created."
fi
