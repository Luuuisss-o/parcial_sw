"""
Test de integracion (sin Maven/Docker real) de exporters/generators/
project_builder.py: verifica que agregar el paso de UAP no rompio nada de
lo que el pipeline ya generaba antes, y que los archivos UAP quedan en el
lugar correcto dentro del arbol Maven.
"""
from pathlib import Path

from exporters.generators.project_builder import build_project


def test_build_project_still_generates_previous_artifacts(tmp_path, diagram_tienda_path):
    out_dir = tmp_path / "project"
    build_project(diagram_tienda_path, str(out_dir))

    java_root = out_dir / "src" / "main" / "java" / "com" / "test"

    # Lo que ya generaba el pipeline antes de agregar UAP -- si esto deja
    # de existir, el wiring nuevo rompio algo que ya funcionaba.
    for entity in ("Cliente", "Producto", "Pedido"):
        assert (java_root / "models" / f"{entity}.java").exists()
        assert (java_root / "repositories" / f"{entity}Repository.java").exists()
        assert (java_root / "services" / f"{entity}Service.java").exists()
        assert (java_root / "controllers" / f"{entity}Controller.java").exists()
        assert (java_root / "dtos" / f"{entity}Dto.java").exists()

    assert (java_root / "controllers" / "HealthController.java").exists()
    assert (out_dir / "pom.xml").exists()
    assert (out_dir / "src" / "main" / "resources" / "application.properties").exists()
    assert (out_dir / "docker-compose.yml").exists()
    assert (out_dir / "Dockerfile").exists()
    assert (out_dir / "README.md").exists()
    assert (out_dir / "postman_collection.json").exists()


def test_build_project_generates_uap_files_in_expected_location(tmp_path, diagram_tienda_path):
    out_dir = tmp_path / "project"
    build_project(diagram_tienda_path, str(out_dir))

    uap_dir = out_dir / "src" / "main" / "java" / "com" / "test" / "uap"
    expected = {
        "UapManifestController.java", "UapSchemaController.java", "UapToolsController.java",
        "UapToolDispatcher.java", "UapSyncController.java", "UapGeneration.java",
        "UapChangeLog.java", "UapCoerce.java", "JacksonTimeZoneConfig.java",
    }
    actual = {p.name for p in uap_dir.iterdir()}
    assert expected == actual


def test_application_properties_sets_timezone(tmp_path, diagram_tienda_path):
    out_dir = tmp_path / "project"
    build_project(diagram_tienda_path, str(out_dir))
    content = (out_dir / "src" / "main" / "resources" / "application.properties").read_text(encoding="utf-8")
    assert "spring.jackson.time-zone=America/La_Paz" in content
    assert "hibernate.jdbc.time_zone=America/La_Paz" in content


def test_dockerfile_sets_timezone(tmp_path, diagram_tienda_path):
    out_dir = tmp_path / "project"
    build_project(diagram_tienda_path, str(out_dir))
    content = (out_dir / "Dockerfile").read_text(encoding="utf-8")
    assert "ENV TZ=America/La_Paz" in content


def test_docker_compose_sets_timezone_on_db_and_app(tmp_path, diagram_tienda_path):
    out_dir = tmp_path / "project"
    build_project(diagram_tienda_path, str(out_dir))
    content = (out_dir / "docker-compose.yml").read_text(encoding="utf-8")
    # "TZ: America/La_Paz" (con exactamente ese espaciado, como linea
    # propia) aparece una vez en "db" y otra en "app" -- ojo que buscar el
    # substring "TZ: America/La_Paz" sin mas matchea tambien dentro de
    # "PGTZ: America/La_Paz", por eso se cuentan lineas exactas.
    lines = content.splitlines()
    assert sum(1 for line in lines if line.strip() == "TZ: America/La_Paz") == 2
    assert "PGTZ: America/La_Paz" in content


def test_readme_documents_uap_endpoints(tmp_path, diagram_tienda_path):
    out_dir = tmp_path / "project"
    build_project(diagram_tienda_path, str(out_dir))
    readme = (out_dir / "README.md").read_text(encoding="utf-8")
    assert "/uap/v1/manifest" in readme
    assert "/uap/v1/tools" in readme
    assert "/uap/v1/sync/state" in readme
