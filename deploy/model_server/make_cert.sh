#!/bin/sh
# Certificado TLS propio del servidor del modelo (llama.cpp sirve HTTPS).
#
#   sh make_cert.sh 18.190.125.22        (IP publica o nombre DNS del servidor)
#
# Es autofirmado: el backend NO confia en "cualquier certificado valido", sino
# SOLO en este (certificate pinning, LOCAL_MODEL_CERT). La clave privada se
# genera aca y nunca sale de este servidor; el certificado (publico) se copia
# al .env del servidor principal.
set -eu
HOST=${1:?Uso: sh make_cert.sh <IP_O_DNS_PUBLICO>}
cd "$(dirname "$0")"
mkdir -p certs
case "$HOST" in
  *[!0-9.]*) SAN="DNS:$HOST" ;;
  *)         SAN="IP:$HOST" ;;
esac
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -days 3650 \
  -keyout certs/key.pem -out certs/cert.pem -subj "/CN=modelo-propio" \
  -addext "subjectAltName=$SAN" \
  -addext "basicConstraints=critical,CA:FALSE" \
  -addext "keyUsage=critical,digitalSignature" \
  -addext "extendedKeyUsage=serverAuth" 2>/dev/null
# Clave privada solo legible por su dueño (llama.cpp corre como root en el
# contenedor y la puede leer igual).
chmod 600 certs/key.pem
chmod 644 certs/cert.pem
echo "Certificado para $SAN (10 años): certs/cert.pem"
