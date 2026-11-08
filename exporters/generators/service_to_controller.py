import os, json
from jinja2 import Environment, FileSystemLoader

def generate_controllers(json_path, output_dir, templates_dir="../templates"):
    """
    Genera un Controller por cada clase del diagrama UML.
    """
    env = Environment(loader=FileSystemLoader(templates_dir))
    template = env.get_template("controller.java.j2")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    diagram = data["diagram"]

    os.makedirs(output_dir, exist_ok=True)

    for c in diagram["classes"]:
        class_name = c["name"]
        file_name = f"{class_name}Controller.java"
        file_path = os.path.join(output_dir, file_name)

        code = template.render(class_name=class_name)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)

        print(f"Generado controller: {file_path}")
