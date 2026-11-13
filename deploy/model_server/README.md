# Servidor del modelo propio (IA local del equipo)

El modelo del equipo (**Gemma 3 1B ajustado con LoRA**, `training/`) corre con **llama.cpp**
en una EC2 aparte. El servidor principal (backend) lo usa como proveedor de IA cuando el dueño
de un diagrama elige *Modelo propio del equipo* en la configuración de la IA del chat.

```
Colab (GPU): entrena ──PUT /models/assistant──► backend (aloja el .gguf)
                                                   │            │
                         cada 10 min (token) ◄─────┘            │ /completion (HTTPS + clave)
EC2 del modelo: sync_model.sh ─► llama.cpp :8080 ◄──────────────┘
celulares: descargan el mismo .gguf y lo corren en el teléfono
```

- Medido con 2 CPU: **5–15 s** por respuesta (edición o revisión).
- El puerto 8080 solo lo alcanza el servidor principal (security group), exige
  `LOCAL_MODEL_API_KEY` y habla **solo HTTPS**: los dos servidores están en cuentas de AWS
  distintas y se hablan por IP pública, así que la clave y las consultas van cifradas.
- El certificado es propio (`make_cert.sh`, autofirmado, 10 años) y el backend confía **solo en
  él** (*certificate pinning*, `LOCAL_MODEL_CERT`): un certificado distinto, aunque sea de una CA
  real, se rechaza. La clave privada nunca sale de la EC2 del modelo.
- Nada de esto llega al navegador: la URL y la clave viven solo en el `.env` del backend.

## 1. Servidor principal: token de sincronización

En la EC2 principal, agregá al `.env` de `~/parcial_sw` un token aleatorio:

```bash
cd ~/parcial_sw
echo "MODEL_SYNC_TOKEN=$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 40)" | sudo tee -a .env
sudo grep MODEL_SYNC_TOKEN .env          # copiá el valor para el paso 3
sudo docker compose -f docker-compose.prod.yml up -d --build backend
```

## 2. Crear la EC2 del modelo (consola de AWS)

- **AMI:** Ubuntu Server 24.04 · **Tipo:** `t3.medium` (2 vCPU, 4 GB) · **Disco:** 20 GB
- **Key pair:** la misma `parcialsw1`
- **IP elástica** para las dos EC2 (si cambian, se corta el enlace y hay que rehacer el certificado)
- **Security group, entrada:**
  - SSH (22) solo desde tu IP
  - TCP **8080** solo desde la IP elástica de la EC2 principal (`<IP>/32`, no desde 0.0.0.0/0).
    Si las dos EC2 están en la misma cuenta y VPC, puede ser el security group de la principal.

## 3. Instalarlo

Desde tu PC, copiá la carpeta y ejecutá el instalador en la EC2 nueva:

```bash
scp -i parcialsw1.pem -r deploy/model_server ubuntu@<IP_PUBLICA_MODELO>:~/
ssh -i parcialsw1.pem ubuntu@<IP_PUBLICA_MODELO>
sh ~/model_server/setup_model_server.sh https://uml-equipo.duckdns.org/api <MODEL_SYNC_TOKEN> <IP_PUBLICA_MODELO>
```

Instala Docker, genera la clave del modelo y el certificado HTTPS para esa IP, descarga el modelo
publicado (verifica el SHA-256), levanta llama.cpp y programa la actualización automática. Al
final imprime tres líneas.

## 4. Conectar el servidor principal

Agregá esas tres líneas al `.env` de la EC2 principal y reconstruí el backend:

```bash
LOCAL_MODEL_URL=https://<IP_PUBLICA_MODELO>:8080
LOCAL_MODEL_API_KEY=<la clave que imprimió el instalador>
LOCAL_MODEL_CERT=<el certificado en base64 que imprimió el instalador>
```
```bash
sudo docker compose -f docker-compose.prod.yml up -d --build backend
```

En la web: chat del diagrama → *Modelo* → **Cambiar** → *Modelo propio del equipo* →
**Guardar y probar conexión** (debe responder "servidor del modelo: ok").

## 5. Entrenar una versión nueva

`training/finetune_colab.ipynb` en Colab con GPU T4 → *Ejecutar todo*. La celda de publicación
la sube al backend; en menos de 10 minutos este servidor la descarga sola y los celulares la
bajan la próxima vez que abren el chat.

## Cambiar la IP o renovar el certificado

```bash
cd ~/model_server
rm -f certs/*.pem && sh make_cert.sh <IP_O_DNS_NUEVO>
sudo docker compose up -d --force-recreate
base64 -w0 certs/cert.pem; echo        # nuevo LOCAL_MODEL_CERT para el .env principal
```

## Operación

```bash
sudo docker logs -f modelo-propio          # llama.cpp
tail -f ~/model_server/sync.log            # actualizaciones del modelo
cat ~/model_server/models/assistant.version
```
