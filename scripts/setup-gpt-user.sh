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

for name in ODOO_DB_NAME ODOO_PASSWORD GPT_ODOO_USER_LOGIN; do
  [[ -n "${!name:-}" ]] || { echo "Missing required variable: $name" >&2; exit 1; }
done

export GPT_ODOO_USER_LOGIN
docker compose run --rm --no-deps -T -e GPT_ODOO_USER_LOGIN web odoo shell \
  -c /etc/odoo/odoo.conf -d "$ODOO_DB_NAME" \
  --db_host=db --db_port=5432 --db_user=odoo --db_password="$ODOO_PASSWORD" <<'PY'
import os
import secrets

login = os.environ["GPT_ODOO_USER_LOGIN"]
group_xmlids = [
    "base.group_user",
    "project.group_project_manager",
    "crm.group_crm_manager",
    "sales_team.group_sale_manager",
    "account.group_account_manager",
    "stock.group_stock_manager",
    "calendar.group_calendar_manager",
]
groups = env["res.groups"]
for xmlid in group_xmlids:
    group = env.ref(xmlid, raise_if_not_found=False)
    if group:
        groups |= group

user = env["res.users"].sudo().search([("login", "=", login)], limit=1)
values = {
    "name": "GPT Odoo Integration",
    "login": login,
    "email": login,
    "active": True,
    "share": False,
    "groups_id": [(6, 0, groups.ids)],
}
if user:
    user.write(values)
else:
    values["password"] = secrets.token_urlsafe(48)
    user = env["res.users"].sudo().create(values)

print(f"GPT_ODOO_USER_ID={user.id}")
PY
