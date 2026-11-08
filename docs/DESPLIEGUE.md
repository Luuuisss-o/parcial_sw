# Despliegue en producción (AWS EC2 + DuckDNS + HTTPS)

Todo el sistema (PostgreSQL, backend FastAPI y frontend React servido por nginx) corre con
`docker-compose.prod.yml` en **un solo servidor**. El script `deploy/setup_ec2.sh` instala lo
necesario, obtiene el certificado HTTPS y levanta los contenedores. Es idempotente: se vuelve a
ejecutar para actualizar el código.

```
Internet ──443──► nginx (frontend)
                    ├─ /               → app React (build estático)
                    ├─ /api/           → backend:8000 (REST + WebSocket)
                    └─ /api/models/    → backend:8000 (subida/descarga del modelo, hasta 4 GB)
                  backend ──► PostgreSQL (volumen pgdata)
                          └─► /app/data/models (volumen assistant_models: el .gguf del celular)
```

## 1. Dominio gratis (DuckDNS)

1. Entrar a <https://www.duckdns.org> con tu cuenta de Google/GitHub.
2. Crear un subdominio, por ejemplo `uml-equipo` → queda `uml-equipo.duckdns.org`.
3. Copiar el **token** que aparece arriba (lo usa el script para apuntar el dominio al servidor).

## 2. Servidor (AWS EC2)

En la consola de AWS → **EC2 → Lanzar instancia**:

| Opción | Valor |
|---|---|
| Imagen (AMI) | **Ubuntu Server 24.04 LTS** |
| Tipo | `t3.small` (2 GB RAM, recomendado). `t3.micro` (1 GB) también funciona: el script agrega 2 GB de swap |
| Par de claves | Crear uno nuevo (`.pem`) y guardarlo |
| Red → grupo de seguridad | Permitir **SSH (22)**, **HTTP (80)** y **HTTPS (443)** desde cualquier lugar |
| Almacenamiento | **30 GB** gp3 (imágenes Docker + modelo de ~1 GB + base de datos) |

Recomendado: **EC2 → IP elásticas → Asignar** y asociarla a la instancia, así la IP no cambia
al reiniciarla (igual, con el token de DuckDNS el script re-registra la IP cada 5 minutos).

## 3. Instalar y levantar todo

Conectarse (desde Git Bash / terminal, en la carpeta donde está el `.pem`):

```bash
ssh -i mi-clave.pem ubuntu@IP_PUBLICA_DE_LA_INSTANCIA
```

En el servidor:

```bash
git clone -b claude/exciting-tesla-sscl8u https://github.com/Luuuisss-o/parcial_sw.git
```

```bash
cd parcial_sw
```

```bash
sudo DOMAIN=uml-equipo.duckdns.org EMAIL=tu@correo.com DUCKDNS_TOKEN=tu-token GEMINI_API_KEY=tu-clave ./deploy/setup_ec2.sh
```

(`GEMINI_API_KEY` es opcional; sin ella la IA de la web no responde, pero el modelo del
celular funciona igual.) La primera vez tarda **10-15 minutos** (compila el frontend). Al final
imprime `OK: https://uml-equipo.duckdns.org`.

> Si el repositorio es privado, `git clone` pide usuario y contraseña: usar un *token* de
> GitHub (Settings → Developer settings → Personal access tokens) como contraseña.

## 4. Crear el usuario administrador

En producción **no** se cargan los usuarios demo (sus contraseñas son públicas). Para publicar
el modelo hace falta un usuario con rol `admin`:

```bash
sudo docker compose -f docker-compose.prod.yml exec backend python -m seeds.create_admin tu@correo.com "Tu Nombre"
```

Pide la contraseña (mínimo 8 caracteres). Si el usuario ya existe (porque te registraste desde
la web), lo promueve a admin.

## 5. Usarlo

| Para | URL |
|---|---|
| Web | `https://uml-equipo.duckdns.org` |
| Documentación de la API | `https://uml-equipo.duckdns.org/api/docs` |
| Notebook de Colab, celda 7 (`API_URL`) | `https://uml-equipo.duckdns.org/api` |
| App móvil (`--dart-define=API_BASE_URL=...`) | `https://uml-equipo.duckdns.org/api` |

## Mantenimiento

```bash
cd ~/parcial_sw && git pull && sudo DOMAIN=uml-equipo.duckdns.org EMAIL=tu@correo.com ./deploy/setup_ec2.sh
```

```bash
sudo docker compose -f docker-compose.prod.yml logs backend --tail 100
```

- El certificado HTTPS se renueva solo (cron diario con `certbot renew`).
- `.env` (en la raíz del repo, en el servidor) guarda las contraseñas generadas al azar; no se
  versiona. Para cambiar la clave de Gemini: editarla ahí y volver a ejecutar el script.
- Los datos (base de datos y modelo) viven en volúmenes de Docker: sobreviven a reinicios y
  actualizaciones. `docker compose down -v` **los borra**.
- Costos: una instancia encendida consume horas aunque nadie la use. Detenerla desde la consola
  cuando no se necesite (la IP elástica sin instancia asociada también cobra).

## Verificado

El stack de producción se levantó completo con estos mismos archivos (certificado de prueba en
lugar de Let's Encrypt): frontend y rutas de la SPA por HTTPS, redirección HTTP→HTTPS, ruta de
renovación de certbot, API, creación de admin, subida de un GGUF de 900 MB por `PUT
/api/models/assistant` a través de nginx (5,6 s, SHA-256 correcto) y descarga parcial con
`Range` (206).
