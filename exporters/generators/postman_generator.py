
# postman_generator.py
import os, json
from exporters.generators.json_to_relations import build_relations, to_camel
from exporters.generators.api_layer import build_api_models

# 🔹 Construir URL en formato Postman (raw, protocol, host, port, path)
def build_url(url_raw: str):
    protocol = "http"
    host = ["localhost"]
    port = "8090"
    path = url_raw.replace("http://localhost:8090/", "").split("/")
    return {
        "raw": url_raw,
        "protocol": protocol,
        "host": host,
        "port": port,
        "path": path
    }

def example_for_java(java_type: str):
    """Valor de ejemplo determinista por tipo Java (mismo diagrama -> misma
    coleccion, sin numeros al azar)."""
    return {
        "Integer": 10,
        "Long": 10,
        "Float": 9.5,
        "Double": 99.9,
        "java.math.BigDecimal": 99.9,
        "Boolean": True,
        "LocalDate": "2026-01-15",
        "LocalDateTime": "2026-01-15T10:30:00",
    }.get(java_type, "Texto de ejemplo")


def generate_postman(json_path, output_dir):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    api_models = {m["class_name"]: m for m in build_api_models(json_path)}

    diagram = data["diagram"]
    relations_map = build_relations(json_path)

    # 📂 Carpeta de archivos individuales
    test_bodies_dir = os.path.join(output_dir, "test_bodies")
    os.makedirs(test_bodies_dir, exist_ok=True)

    # Una sola coleccion con todas las clases agrupadas en carpetas: mas
    # comodo para importar en Postman de una vez en lugar de un archivo por
    # clase. Los archivos sueltos en test_bodies/ se siguen generando igual,
    # por si se quiere importar solo el CRUD de una clase puntual.
    all_folders = [
        {
            "name": "Health",
            "item": [
                {
                    "name": "Health check",
                    "request": {"method": "GET", "url": build_url("http://localhost:8090/")},
                }
            ],
        }
    ]

    for c in diagram["classes"]:
        class_name = c["name"]
        url_base = f"http://localhost:8090/api/{class_name.lower()}s"
        attributes = c.get("attributes", [])

        # 🔹 Body de ejemplo = el DTO real de la API (ver api_layer.py):
        # atributos (incluidos los heredados) y relaciones escribibles como
        # ids. Antes usaba nombres que no coincidian con la entidad
        # ("productos" vs "producto") y objetos anidados que se ignoraban.
        model = api_models[class_name]
        body = {a["name"]: example_for_java(a["type"]) for a in model["attrs"]}
        for r in model["owner_rels"]:
            body[r["dto_field"]] = [1] if r["is_list"] else 1

        # 🔹 CRUD con build_url
        requests = [
            {
                "name": f"Create {class_name}",
                "request": {
                    "method": "POST",
                    "header": [{"key": "Content-Type", "value": "application/json"}],
                    "body": {"mode": "raw", "raw": json.dumps(body, indent=2, ensure_ascii=False)},
                    "url": build_url(url_base)
                }
            },
            {
                "name": f"Get All {class_name}",
                "request": {"method": "GET", "url": build_url(url_base)}
            },
            {
                "name": f"Get {class_name} by ID",
                "request": {"method": "GET", "url": build_url(f"{url_base}/1")}
            },
            {
                "name": f"Update {class_name}",
                "request": {
                    "method": "PUT",
                    "header": [{"key": "Content-Type", "value": "application/json"}],
                    "body": {"mode": "raw", "raw": json.dumps(body, indent=2, ensure_ascii=False)},
                    "url": build_url(f"{url_base}/1")
                }
            },
            {
                "name": f"Delete {class_name}",
                "request": {"method": "DELETE", "url": build_url(f"{url_base}/1")}
            }
        ]

        # 👉 Guardar CRUD por clase
        model_collection = {
            "info": {
                "name": f"{class_name} API",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
            },
            "item": requests
        }

        file_path = os.path.join(test_bodies_dir, f"{class_name}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(model_collection, f, indent=2, ensure_ascii=False)

        all_folders.append({"name": class_name, "item": requests})

        print(f"CRUD Postman generado: {file_path}")

    # Coleccion unica con todas las clases, lista para importar y correr
    # directo contra el backend generado (levantalo antes con
    # docker-compose up y ./mvnw spring-boot:run, ver README del ZIP).
    full_collection = {
        "info": {
            "name": f"{diagram.get('title', 'Backend generado')} - API",
            "description": "Generado automaticamente a partir del diagrama UML. Requiere el backend Spring Boot corriendo en localhost:8090 (ver README.md del proyecto exportado).",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": all_folders,
    }
    full_path = os.path.join(output_dir, "postman_collection.json")
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(full_collection, f, indent=2, ensure_ascii=False)
    print(f"Coleccion Postman unificada generada: {full_path}")
