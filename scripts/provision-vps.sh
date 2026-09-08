#!/usr/bin/env bash
set -Eeuo pipefail

[[ "$EUID" -eq 0 ]] || { echo 'Run as root.' >&2; exit 1; }
: "${DEPLOY_USER:=odoo-deploy}"
: "${DEPLOY_PATH:=/var/www/apps/odoo-proyectos}"
: "${REPO_URL:?Set REPO_URL to the Git repository URL}"
: "${DOMAIN:?Set DOMAIN to the public Odoo domain}"
: "${DEPLOY_PUBLIC_KEY:?Set DEPLOY_PUBLIC_KEY to the GitHub Actions public key}"

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl git gettext-base ufw debian-keyring debian-archive-keyring apt-transport-https
curl -fsSL https://get.docker.com | sh

id "$DEPLOY_USER" >/dev/null 2>&1 || useradd --create-home --shell /bin/bash "$DEPLOY_USER"
usermod -aG docker "$DEPLOY_USER"
install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"
printf '%s\n' "$DEPLOY_PUBLIC_KEY" > "/home/$DEPLOY_USER/.ssh/authorized_keys"
chown "$DEPLOY_USER:$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh/authorized_keys"
chmod 600 "/home/$DEPLOY_USER/.ssh/authorized_keys"

install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$DEPLOY_PATH"
if [[ ! -d "$DEPLOY_PATH/.git" ]]; then
  runuser -u "$DEPLOY_USER" -- git clone "$REPO_URL" "$DEPLOY_PATH"
fi
install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$DEPLOY_PATH/backups"

cat > "/etc/cron.d/odoo-backup" <<EOF
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
0 2 * * * $DEPLOY_USER cd $DEPLOY_PATH && /usr/bin/bash scripts/backup.sh >> /var/log/odoo-backup.log 2>&1
EOF
chmod 644 /etc/cron.d/odoo-backup

curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y caddy
cat > /etc/caddy/Caddyfile <<EOF
$DOMAIN {
    reverse_proxy 127.0.0.1:8069
}
EOF
systemctl enable --now caddy
systemctl reload caddy

ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
echo "VPS provisioned. Create $DEPLOY_PATH/.env with values from .env.example before the first deployment."
