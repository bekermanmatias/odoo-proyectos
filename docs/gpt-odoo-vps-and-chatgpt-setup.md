# Activación de GPT ↔ Odoo

## 1. Preparar secretos y usuario técnico en el VPS

No subas ningún secreto a Git. En el VPS, como `odoo-deploy`:

```bash
cd /var/www/apps/odoo-proyectos
openssl rand -hex 32
nano .env
```

Agregá el valor generado como `GPT_ODOO_API_KEY`, conservá `ODOO_DB_NAME=pap` y dejá `GPT_ODOO_USER_ID=0` por ahora. Tras desplegar el addon, ejecutá:

```bash
bash scripts/setup-gpt-user.sh
```

Copiá la línea `GPT_ODOO_USER_ID=...` que imprime el script a `.env`, reiniciá Odoo y verificá la API desde el VPS sin mostrar la clave:

```bash
set -a
source .env
set +a
docker compose up -d web
curl --fail -H "Authorization: Bearer $GPT_ODOO_API_KEY" http://127.0.0.1:8069/gpt-api/v1/capabilities
```

El script crea o actualiza un usuario interno `gpt-odoo-integration@pupuia.local`. No es administrador y no debe usarse para iniciar sesión.

## 2. Publicar únicamente la API

En Hostinger creá el registro DNS **A** `api` apuntando a la IP del VPS. Cuando propague, como `root` en el VPS:

```bash
cp /var/www/apps/odoo-proyectos/docs/nginx-api.pupuia.com.conf /etc/nginx/sites-available/api.pupuia.com
printf '%s\n' 'limit_req_zone $binary_remote_addr zone=gpt_odoo_api:10m rate=30r/m;' > /etc/nginx/conf.d/gpt-odoo-rate-limit.conf
ln -s /etc/nginx/sites-available/api.pupuia.com /etc/nginx/sites-enabled/api.pupuia.com
nginx -t
systemctl reload nginx
certbot --nginx -d api.pupuia.com
```

Verificá que `https://api.pupuia.com/gpt-api/openapi.json` responda JSON y que `https://api.pupuia.com/` responda 404. No publiques ninguna otra ruta de Odoo en ese subdominio.

## 3. Conectar ChatGPT Plus

En ChatGPT, creá o editá tu GPT, abrí **Configure → Actions → Create new action** y:

1. Importá `https://api.pupuia.com/gpt-api/openapi.json` o pegá su contenido.
2. Elegí autenticación **API key**, tipo **Bearer**.
3. Pegá exactamente el valor de `GPT_ODOO_API_KEY`.
4. Copiá las instrucciones de `docs/chatgpt-gpt-instructions.md` al campo **Instructions**.
5. En Preview ejecutá `Consultá las capacidades disponibles de Odoo`.

Luego probá una creación no sensible: `Creá una tarea llamada Revisar propuesta en el proyecto Ventas, para mañana`. Para borrar, confirmar una cotización, contabilizar una factura o validar un movimiento, el GPT debe mostrar la propuesta y esperar un “Confirmo”.
