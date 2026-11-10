#!/bin/sh
# Descarga la ultima version del modelo publicada en el backend (la que sube
# el notebook de Colab con PUT /models/assistant) y reinicia llama.cpp.
# Lo corre cron cada 10 minutos (ver setup_model_server.sh): despues de
# entrenar en Colab no hace falta tocar este servidor.
set -eu
cd "$(dirname "$0")"
. ./.env   # BACKEND_URL, MODEL_SYNC_TOKEN, LOCAL_MODEL_API_KEY

mkdir -p models
manifest=$(curl -fsS -H "X-Model-Sync-Token: $MODEL_SYNC_TOKEN" "$BACKEND_URL/models/assistant")
field() { printf '%s' "$manifest" | python3 -c "import sys,json; print(json.load(sys.stdin).get('$1') or '')"; }

if [ "$(field available)" != "True" ]; then
  echo "$(date -Is) el backend todavia no tiene un modelo publicado"
  exit 0
fi
sha=$(field sha256)
version=$(field version)
if [ -f models/assistant.sha256 ] && [ "$(cat models/assistant.sha256)" = "$sha" ]; then
  exit 0  # ya esta la ultima version
fi

echo "$(date -Is) descargando la version $version"
curl -fsS -C - -H "X-Model-Sync-Token: $MODEL_SYNC_TOKEN" \
  -o models/assistant.gguf.part "$BACKEND_URL/models/assistant/download"
echo "$sha  models/assistant.gguf.part" | sha256sum -c -   # integridad antes de usarlo
mv models/assistant.gguf.part models/assistant.gguf
echo "$sha" > models/assistant.sha256
echo "$version" > models/assistant.version

docker compose up -d --force-recreate llama
echo "$(date -Is) modelo $version en servicio"
