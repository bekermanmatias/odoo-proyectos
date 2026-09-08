# odoo-proyectos

## Desarrollo local

1. Copiar `.env.example` a `.env` y reemplazar sus valores.
2. Generar la configuración local: `envsubst '${ODOO_ADMIN_PASSWORD}' < config/odoo.conf.template > config/odoo.conf`.
3. Ejecutar `docker compose up -d --build`.
4. Abrir `http://127.0.0.1:8069`.

## Despliegue en VPS

El despliegue de producción se ejecuta desde GitHub Actions al hacer push a `main`.
Configurar estos secrets en el environment `production`:

- `VPS_SSH_PRIVATE_KEY`: clave privada Ed25519 dedicada para GitHub Actions.
- `VPS_HOST`: IP o hostname del VPS.
- `VPS_USER`: normalmente `odoo-deploy`.
- `VPS_DEPLOY_PATH`: normalmente `/var/www/apps/odoo-proyectos`.

En el VPS debe existir `.env` con los valores de `.env.example`. No subirlo al repositorio.
La provisión crea un backup diario a las 02:00 UTC y conserva 14 días de backups.

Para un VPS limpio, ejecutar como root, definiendo `REPO_URL`, `DOMAIN` y `DEPLOY_PUBLIC_KEY`:

```bash
REPO_URL=git@github.com:bekermanmatias/odoo-proyectos.git \
DOMAIN=odoo.example.com \
DEPLOY_PUBLIC_KEY='ssh-ed25519 AAAA...' \
bash ./scripts/provision-vps.sh
```

Antes de activar producción, rotar la contraseña maestra de Odoo que estuvo versionada históricamente y generar valores nuevos para `.env`.
