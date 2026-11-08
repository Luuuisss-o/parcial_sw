# model_to_repository.py
import os, json
from jinja2 import Environment, FileSystemLoader

def generate_repositories(json_path, output_dir, templates_dir="../templates"):
    # Configurar Jinja2
    env = Environment(loader=FileSystemLoader(templates_dir))
    template = env.get_template("repository.java.j2")

    # Leer JSON con las clases UML
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    diagram = data["diagram"]
    os.makedirs(output_dir, exist_ok=True)

    # Generar repositorio por cada clase
    for c in diagram["classes"]:
        class_name = c["name"]
        file_name = f"{class_name}Repository.java"
        file_path = os.path.join(output_dir, file_name)

        code = template.render(class_name=class_name)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)

        print(f"Generado repositorio: {file_path}")
