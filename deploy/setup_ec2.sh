#!/usr/bin/env bash
# deploy/setup_ec2.sh
#
# Despliegue completo (PostgreSQL + backend FastAPI + frontend React/nginx con
# HTTPS) en una instancia Ubuntu 24.04 recién creada (AWS EC2 u otra VPS).
# Es idempotente: se puede volver a correr para actualizar el código.
#
# Uso (desde la carpeta del repo clonado en el servidor):
#   sudo DOMAIN=mi-uml.duckdns.org EMAIL=yo@gmail.com DUCKDNS_TOKEN=xxxx ./deploy/setup_ec2.sh
#
#   DOMAIN         dominio que apunta a la IP pública del servidor (obligatorio)
#   EMAIL          correo para Let's Encrypt (avisos de vencimiento) (obligatorio)
#   DUCKDNS_TOKEN  si el dominio es de DuckDNS: actualiza la IP sola (opcional)
#   GEMINI_API_KEY clave de Gemini para el asistente de IA web (opcional; se puede
#                  agregar después en .env y re-ejecutar)
set -euo pipefail

: "${DOMAIN:?Falta DOMAIN (ej. DOMAIN=mi-uml.duckdns.org)}"
: "${EMAIL:?Falta EMAIL (correo para avisos de Lets Encrypt)}"
[ "$(id -u)" -eq 0 ] || { echo "Ejecutalo con sudo"; exit 1; }

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
COMPOSE="docker compose -f docker-compose.prod.yml"
step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

step "1/7 Memoria swap (el build del frontend no entra en 1-2 GB de RAM)"
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
swapon --show

step "2/7 Docker, certbot y utilidades"
if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y docker.io docker-compose-v2 certbot git curl openssl
  systemctl enable --now docker
fi
command -v certbot >/dev/null || apt-get install -y certbot
docker compose version

step "3/7 DNS: $DOMAIN -> IP pública de este servidor"
PUBLIC_IP="$(curl -fsS https://checkip.amazonaws.com | tr -d '[:space:]')"
if [ -n "${DUCKDNS_TOKEN:-}" ]; then
  SUB="${DOMAIN%.duckdns.org}"
  curl -fsS "https://www.duckdns.org/update?domains=${SUB}&token=${DUCKDNS_TOKEN}&ip=" && echo
  # Si la IP del servidor cambia (reinicio sin IP elástica), se re-registra sola.
  echo "*/5 * * * * root curl -fsS 'https://www.duckdns.org/update?domains=${SUB}&token=${DUCKDNS_TOKEN}&ip=' >/dev/null" > /etc/cron.d/duckdns
  chmod 600 /etc/cron.d/duckdns
fi
for i in $(seq 1 30); do
  RESOLVED="$(getent ahostsv4 "$DOMAIN" | awk 'NR==1{print $1}' || true)"
  [ "$RESOLVED" = "$PUBLIC_IP" ] && break
  echo "  $DOMAIN resuelve a '${RESOLVED:-nada}', se espera $PUBLIC_IP (reintento $i/30)"; sleep 10
done
[ "$RESOLVED" = "$PUBLIC_IP" ] || { echo "El dominio no apunta a este servidor: revisá el DNS"; exit 1; }

step "4/7 Variables de entorno (.env, no se versiona)"
if [ ! -f .env ]; then
  cat > .env <<EOF
DOMAIN=$DOMAIN
DB_NAME=parcial_sw
DB_USER=postgres
DB_PASSWORD=$(openssl rand -hex 24)
JWT_SECRET=$(openssl rand -hex 32)
GEMINI_API_KEY=${GEMINI_API_KEY:-}
SEED_DEMO=false
EOF
  chmod 600 .env
  echo "  .env creado con contraseñas aleatorias"
else
  sed -i "s/^DOMAIN=.*/DOMAIN=$DOMAIN/" .env
  if [ -n "${GEMINI_API_KEY:-}" ]; then
    grep -q '^GEMINI_API_KEY=' .env && sed -i "s|^GEMINI_API_KEY=.*|GEMINI_API_KEY=$GEMINI_API_KEY|" .env \
      || echo "GEMINI_API_KEY=$GEMINI_API_KEY" >> .env
  fi
  echo "  .env existente conservado"
fi

step "5/7 Certificado HTTPS (Let's Encrypt)"
mkdir -p /var/www/certbot
if [ ! -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
  $COMPOSE stop frontend 2>/dev/null || true   # libera el puerto 80
  certbot certonly --standalone --non-interactive --agree-tos -m "$EMAIL" -d "$DOMAIN"
fi
# Renovación: certbot usa el webroot que sirve nginx y luego lo recarga.
cat > /etc/cron.d/certbot-renew <<EOF
17 3 * * * root certbot renew --quiet --webroot -w /var/www/certbot --deploy-hook "docker exec uml-diagramador-frontend nginx -s reload"
EOF

step "6/7 Construir y levantar contenedores (la primera vez tarda 5-10 min)"
$COMPOSE up -d --build
docker image prune -f >/dev/null

step "7/7 Verificación"
for i in $(seq 1 40); do
  curl -fsS -o /dev/null "https://$DOMAIN/api/docs" && break
  sleep 5
done
if curl -fsS -o /dev/null "https://$DOMAIN/api/docs"; then
  echo "  OK: https://$DOMAIN (frontend) y https://$DOMAIN/api/docs (API)"
else
  echo "  La API todavía no responde. Revisá: $COMPOSE logs backend --tail 80"; exit 1
fi

cat <<EOF

Listo. Siguiente paso: crear tu usuario administrador (pide la contraseña):

  sudo $COMPOSE exec backend python -m seeds.create_admin TU_EMAIL "Tu Nombre"

URL para el notebook de Colab (celda 7) y para la app móvil (API_BASE_URL):
  https://$DOMAIN/api
EOF
