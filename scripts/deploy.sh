#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$APP_DIR"

required=(ODOO_PASSWORD POSTGRES_PASSWORD ODOO_ADMIN_PASSWORD ODOO_DB_NAME ODOO_MODULES HEALTHCHECK_URL)
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
for name in "${required[@]}"; do
  [[ -n "${!name:-}" ]] || { echo "Missing required variable: $name" >&2; exit 1; }
done

previous_commit="$(git rev-parse HEAD)"
backup_file=""
rollback() {
  trap - ERR
  echo "Deployment failed; rolling back code to $previous_commit" >&2
  git reset --hard "$previous_commit" >/dev/null
  render_config
  if [[ -n "$backup_file" && -f "$backup_file" ]]; then
    echo "Restoring database backup $backup_file" >&2
    docker compose up -d db
    docker compose stop web >/dev/null 2>&1 || true
    docker compose exec -T db dropdb --if-exists -U odoo "$ODOO_DB_NAME" >/dev/null
    docker compose exec -T db createdb -U odoo "$ODOO_DB_NAME"
    gunzip -c "$backup_file" | docker compose exec -T db pg_restore -U odoo -d "$ODOO_DB_NAME" --no-owner --clean --if-exists
  fi
  docker compose up -d --build
}
trap rollback ERR

render_config() {
  command -v envsubst >/dev/null || { echo 'gettext-base/envsubst is required' >&2; exit 1; }
  umask 022
  chmod 755 config
  rm -f config/odoo.conf
  envsubst '${ODOO_ADMIN_PASSWORD} ${ODOO_DB_NAME}' < config/odoo.conf.template > config/odoo.conf
  # The Odoo container runs as the `odoo` user, not as the VPS deploy user.
  chmod 644 config/odoo.conf
}

git fetch origin main
git checkout main
git reset --hard origin/main
render_config

mkdir -p backups
docker compose up -d db
docker compose exec -T db pg_isready -U odoo -d postgres
if docker compose exec -T db psql -U odoo -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$ODOO_DB_NAME'" | grep -q 1; then
  backup_file="backups/odoo-${ODOO_DB_NAME}-$(date -u +%Y%m%dT%H%M%SZ).dump.gz"
  docker compose exec -T db pg_dump -U odoo -Fc "$ODOO_DB_NAME" | gzip > "$backup_file"
fi
find backups -type f -name '*.dump.gz' -mtime +14 -delete

docker compose build web
docker compose run --rm --no-deps --entrypoint sh web -c 'id; ls -ld /etc/odoo; ls -l /etc/odoo/odoo.conf; test -r /etc/odoo/odoo.conf; head -n 4 /etc/odoo/odoo.conf'
module_list="$(tr ' ' ',' <<< "$ODOO_MODULES")"
if docker compose exec -T db psql -U odoo -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$ODOO_DB_NAME'" | grep -q 1; then
  docker compose run --rm web odoo \
    -c /etc/odoo/odoo.conf -d "$ODOO_DB_NAME" \
    --db_host=db --db_port=5432 --db_user=odoo --db_password="$ODOO_PASSWORD" \
    --update="$module_list" --stop-after-init --no-http
else
  docker compose run --rm web odoo \
    -c /etc/odoo/odoo.conf -d "$ODOO_DB_NAME" \
    --db_host=db --db_port=5432 --db_user=odoo --db_password="$ODOO_PASSWORD" \
    --init="base,$module_list" --without-demo=1 --stop-after-init --no-http
fi
docker compose up -d web

for attempt in {1..30}; do
  if curl --fail --silent --show-error --max-time 10 "$HEALTHCHECK_URL" >/dev/null; then
    trap - ERR
    echo "Deployment successful: $(git rev-parse --short HEAD)"
    exit 0
  fi
  sleep 10
done
echo "Healthcheck failed: $HEALTHCHECK_URL" >&2
rollback
exit 1
