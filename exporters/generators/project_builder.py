# exporters/generators/project_builder.py
import os
from exporters.generators.json_to_full_orm import generate_from_json
from exporters.generators.model_to_repository import generate_repositories
from exporters.generators.api_layer import generate_api_layer
from exporters.generators.postman_generator import generate_postman
from exporters.generators.uap_generator import generate_uap

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")

def render_template(template_path, context):
    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read().lstrip()
    for key, value in context.items():
        content = content.replace("{{ " + key + " }}", value)
    return content


def build_project(json_path: str, output_dir: str):
    src_main = os.path.join(output_dir, "src", "main", "java", "com", "test")
    src_models = os.path.join(src_main, "models")
    src_repositories = os.path.join(src_main, "repositories")
    src_services = os.path.join(src_main, "services")
    src_controllers = os.path.join(src_main, "controllers")
    src_dtos = os.path.join(src_main, "dtos")
    src_uap = os.path.join(src_main, "uap")
    resources = os.path.join(output_dir, "src", "main", "resources")

    os.makedirs(src_main, exist_ok=True)
    os.makedirs(src_models, exist_ok=True)
    os.makedirs(src_repositories, exist_ok=True)
    os.makedirs(src_services, exist_ok=True)
    os.makedirs(src_controllers, exist_ok=True)
    os.makedirs(src_dtos, exist_ok=True)
    os.makedirs(src_uap, exist_ok=True)
    os.makedirs(resources, exist_ok=True)

    # 1) Generar modelos
    generate_from_json(json_path, src_models)

    # 2) Repositorios
    generate_repositories(json_path, src_repositories, TEMPLATES_DIR)

    # 3-5) DTOs, Servicios, Controladores y manejo de errores (api_layer.py)
    generate_api_layer(json_path, src_main, TEMPLATES_DIR)

    # 6) Protocolo UAP (manifest/schema/tools/invoke/sync) -- se genera
    # despues de los DTOs porque reusa el mismo modelo de atributos, y
    # antes de Postman por si en el futuro la coleccion incluye tambien
    # los endpoints de UAP.
    generate_uap(json_path, src_uap, TEMPLATES_DIR)

    # 7) Postman
    generate_postman(json_path, output_dir)

    # 8) Archivos fijos (HealthController, pom.xml, application.properties, etc.)
    health_content = render_template(
        os.path.join(TEMPLATES_DIR, "health_controller.java.j2"),
        {"groupId": "com.test"}
    )
    with open(os.path.join(src_controllers, "HealthController.java"), "w", encoding="utf-8") as f:
        f.write(health_content)

    pom_content = render_template(
        os.path.join(TEMPLATES_DIR, "pom.xml.j2"),
        {"groupId": "com.test", "artifactId": "demo"}
    )
    with open(os.path.join(output_dir, "pom.xml"), "w", encoding="utf-8") as f:
        f.write(pom_content)

    db_context = {"db_name": "testdb", "db_user": "postgres", "db_pass": "1234"}

    props_content = render_template(
        os.path.join(TEMPLATES_DIR, "application.properties.j2"),
        db_context
    )
    with open(os.path.join(resources, "application.properties"), "w", encoding="utf-8") as f:
        f.write(props_content)

    main_class_content = render_template(
        os.path.join(TEMPLATES_DIR, "main.java.j2"),
        {"groupId": "com.test", "artifactId": "demo"}
    )
    with open(os.path.join(src_main, "DemoApplication.java"), "w", encoding="utf-8") as f:
        f.write(main_class_content)

    compose_content = render_template(
        os.path.join(TEMPLATES_DIR, "docker-compose.yml.j2"),
        {**db_context, "artifactId": "demo"}
    )
    with open(os.path.join(output_dir, "docker-compose.yml"), "w", encoding="utf-8") as f:
        f.write(compose_content)

    dockerfile_content = render_template(
        os.path.join(TEMPLATES_DIR, "Dockerfile.j2"),
        {"artifactId": "demo"}
    )
    with open(os.path.join(output_dir, "Dockerfile"), "w", encoding="utf-8") as f:
        f.write(dockerfile_content)

    readme_content = render_readme(db_context)
    with open(os.path.join(output_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write(readme_content)

    print(f"Proyecto generado en: {output_dir}")


def render_readme(db_context: dict) -> str:
    return f"""# Backend generado (Spring Boot)

Generado automaticamente a partir del diagrama UML del editor colaborativo.
Es un proyecto aparte, independiente del diagramador: corre en sus propios
contenedores Docker, con su propia base de datos.

## 1. Levantar todo (backend + base de datos)

Requiere Docker Desktop instalado y corriendo. Un solo comando levanta los
dos contenedores (la app Spring Boot y su Postgres):

```bash
docker compose up -d --build
```

La primera vez tarda un par de minutos (Maven descarga dependencias y
compila dentro del contenedor). El backend espera a que la base de datos
este lista antes de arrancar.

El backend queda escuchando en **http://localhost:8090**. Con
`spring.jpa.hibernate.ddl-auto=update` (ver `application.properties`),
Hibernate crea las tablas que falten al arrancar, sin borrar los datos ya
cargados -- no hace falta correr ningun script SQL a mano. Para empezar con
la base vacia: `DDL_AUTO=create docker compose up -d`.

Credenciales: `docker-compose.yml` toma `DB_NAME`, `DB_USER` y
`DB_PASSWORD` de un archivo `.env` junto a el (si no existe, usa los
valores de desarrollo de la tabla de abajo). Para un despliegue real,
crea ese `.env` con una contrasena propia.

## API REST

Cada clase del diagrama tiene su CRUD en `/api/<clase>s` (ej.
`/api/pedidos`). Entra y sale un DTO con el `id`, los atributos y las
relaciones como ids: `clienteId` (a-uno) o `productoIds` (a-muchos). Las
relaciones del lado inverso se devuelven pero son de solo lectura (se
asignan desde la otra clase).

| Metodo | Ruta | Respuesta |
|---|---|---|
| GET | `/api/<clase>s` | 200, lista |
| GET | `/api/<clase>s/{id}` | 200, o 404 si no existe |
| POST | `/api/<clase>s` | 201 creado; 400 si falta un campo obligatorio o un id referenciado no existe |
| PUT | `/api/<clase>s/{id}` | 200 (reemplaza todos los campos), o 404 |
| DELETE | `/api/<clase>s/{id}` | 204, 404, o 409 si otro registro todavia lo referencia |

Los errores vienen como JSON con un `message` legible.

El backend genera el CRUD completo de lo que el diagrama expresa; reglas de
negocio que el diagrama no describe (calculos, estados, permisos) hay que
programarlas aparte en los `services/`.

Probar que levanto bien:

```bash
curl http://localhost:8090/
```

Ver logs en vivo:

```bash
docker compose logs -f app
```

Para parar todo (sin perder los datos de la base):

```bash
docker compose stop
```

Para parar y borrar los contenedores (los datos de la base se mantienen,
viven en un volumen aparte):

```bash
docker compose down
```

## 2. Probar los endpoints con Postman

Importar `postman_collection.json` (en la raiz de este proyecto) directo en
Postman: ya trae una carpeta por clase con el CRUD completo (Create, Get
All, Get by ID, Update, Delete) apuntando a `localhost:8090`, mas un
request de Health check. No hace falta configurar nada mas, los bodies de
ejemplo ya vienen armados con datos de prueba.

## 3. Conectarse a la base con DBeaver (u otro cliente SQL)

El contenedor de la base expone su puerto hacia la PC, asi que se conecta
igual que a cualquier Postgres local:

| Campo     | Valor              |
|-----------|---------------------|
| Host      | localhost           |
| Puerto    | 5434                |
| Base      | {db_context['db_name']} |
| Usuario   | {db_context['db_user']} |
| Password  | {db_context['db_pass']} |

Nota: el puerto es 5434, no el 5432 estandar de Postgres -- se eligio asi
a proposito para no chocar ni con el 5432 estandar ni con el 5433 que ya
usa la base del diagramador, en caso de que tengas los dos proyectos
corriendo al mismo tiempo.

Las tablas aparecen recien despues de que el contenedor `app` arranque una
vez, porque las crea Hibernate al levantar.

## Correrlo sin Docker (alternativa)

Si preferis no usar Docker para el backend (solo para la base de datos, por
ejemplo), podes levantar unicamente el contenedor de Postgres:

```bash
docker compose up -d db
```

Y correr el backend directo con Maven, apuntando a `localhost:5434`
(el default si no se setean `DB_HOST`/`DB_PORT`):

```bash
mvn spring-boot:run
```

## 4. Protocolo UAP (para el asistente de IA local del movil)

Ademas del CRUD REST clasico (`/api/...`), este backend expone un
protocolo de descubrimiento generico -- pensado para que un cliente que no
conoce el dominio de antemano (por ejemplo, el asistente de IA que corre
localmente en la app movil) pueda enterarse solo, en tiempo de ejecucion,
que entidades y operaciones existen acá.

Descubrir que hay:

```bash
curl http://localhost:8090/uap/v1/manifest
curl http://localhost:8090/uap/v1/tools
curl http://localhost:8090/uap/v1/schema
```

Ejecutar una operacion (ejemplo generico, el nombre de la entidad y sus
campos van a depender del diagrama con el que se genero este backend):

```bash
curl -X POST http://localhost:8090/uap/v1/tools/create_<entidad>/invoke \\
  -H "Content-Type: application/json" \\
  -d '{{"clientRecordId": "un-uuid-cualquiera", "input": {{"campo": "valor"}}}}'
```

Sincronizacion (para un cliente offline-first que necesita saber que
cambio desde la ultima vez que se conecto):

```bash
curl http://localhost:8090/uap/v1/sync/state
curl "http://localhost:8090/uap/v1/sync/changes?since=0"
```

Notas:
- Sin autenticacion (`GET /uap/v1/permissions` lo declara explicitamente
  con `"mode": "open"`) -- coherente con que el CRUD REST clasico tampoco
  la tiene.
- `generation` (en `/uap/v1/manifest` y `/uap/v1/sync/state`) cambia cada
  vez que se reinicia el contenedor `app` (porque `ddl-auto=create` recrea
  el schema en cada arranque): un cliente que cachea datos localmente debe
  descartar su cache si ese valor no coincide con el que tenia guardado.
- El log de sincronizacion (`uap_change_log`) solo registra cambios hechos
  A TRAVES de UAP (`/uap/v1/tools/.../invoke` o `/uap/v1/sync/push`), no
  los hechos contra el CRUD REST clasico (`/api/...`).
"""
