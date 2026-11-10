#!/bin/sh
# Instala el servidor del modelo propio en una EC2 Ubuntu nueva (t3.medium).
#
#   sh setup_model_server.sh https://uml-equipo.duckdns.org/api <MODEL_SYNC_TOKEN>
#
# MODEL_SYNC_TOKEN es el mismo valor que se puso en el .env del servidor
# principal (ver deploy/model_server/README.md).
set -eu
BACKEND_URL=${1:?Uso: sh setup_model_server.sh <BACKEND_URL> <MODEL_SYNC_TOKEN>}
MODEL_SYNC_TOKEN=${2:?Falta MODEL_SYNC_TOKEN}
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

step() { printf '\n==> %s\n' "$1"; }

step "1/4 Docker"
if ! command -v docker >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq docker.io docker-compose-v2 curl python3
  sudo usermod -aG docker "$USER"
fi

step "2/4 Configuracion (.env, no se versiona)"
if [ ! -f .env ]; then
  KEY=$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 40)
  printf 'BACKEND_URL=%s\nMODEL_SYNC_TOKEN=%s\nLOCAL_MODEL_API_KEY=%s\n' "$BACKEND_URL" "$MODEL_SYNC_TOKEN" "$KEY" > .env
  chmod 600 .env
fi
. ./.env

step "3/4 Modelo (descarga ~0,8 GB y verifica el SHA-256)"
chmod +x sync_model.sh
sudo -E sh -c "cd '$DIR' && ./sync_model.sh"
sudo docker compose up -d

step "4/4 Actualizacion automatica (cada 10 minutos)"
( sudo crontab -l 2>/dev/null | grep -v sync_model.sh || true
  echo "*/10 * * * * cd $DIR && ./sync_model.sh >> $DIR/sync.log 2>&1" ) | sudo crontab -

for i in $(seq 1 60); do
  sudo docker exec modelo-propio true 2>/dev/null && \
    curl -fsS -H "Authorization: Bearer $LOCAL_MODEL_API_KEY" http://localhost:8080/health >/dev/null 2>&1 && break
  sleep 2
done
IP=$(hostname -I | awk '{print $1}')
cat <<EOF

Listo. Agregá esto al .env del servidor PRINCIPAL y reconstruí su backend:

  LOCAL_MODEL_URL=http://$IP:8080
  LOCAL_MODEL_API_KEY=$LOCAL_MODEL_API_KEY

  sudo docker compose -f docker-compose.prod.yml up -d --build backend
EOF
