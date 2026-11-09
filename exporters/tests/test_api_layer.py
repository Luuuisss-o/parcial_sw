"""
Regresiones del backend generado que se encontraron al compilarlo y
probarlo de verdad (Maven + PostgreSQL + CRUD real). Estos tests fijan el
codigo generado; la prueba de punta a punta (compilar, levantar y hacer el
CRUD) esta descrita en docs/estado-1p.md.
"""
import json
from pathlib import Path

import pytest

from exporters.generators.api_layer import build_api_models
from exporters.generators.project_builder import build_project


@pytest.fixture
def project(tmp_path, diagram_tienda_path) -> Path:
    out = tmp_path / "project"
    build_project(diagram_tienda_path, str(out))
    return out


def _java(project: Path, rel: str) -> str:
    return (project / "src" / "main" / "java" / "com" / "test" / rel).read_text(encoding="utf-8")


def test_entities_expose_relations_with_accessors_hidden_from_json(project):
    # Antes los campos de relacion no tenian getters/setters: Pedido.cliente
    # no se podia asignar ni leer por la API.
    pedido = _java(project, "models/Pedido.java")
    assert "public Cliente getCliente()" in pedido
    assert "public void setCliente(Cliente cliente)" in pedido
    # @JsonIgnore justo antes del getter: sin recursion infinita al serializar.
    assert "@JsonIgnore\n    public Cliente getCliente()" in pedido


def test_dto_carries_id_attributes_and_relations_as_ids(project):
    dto = _java(project, "dtos/PedidoDto.java")
    for field in ("private Long id;", "private LocalDate fecha;", "private Long clienteId;"):
        assert field in dto
    assert "List<Long>" in dto  # productos como lista de ids


def test_controller_uses_dto_and_never_returns_optional(project):
    ctrl = _java(project, "controllers/PedidoController.java")
    assert "Optional" not in ctrl  # GET /{id} devolvia {"present": true}
    assert "PedidoDto getById(" in ctrl
    assert "@ResponseStatus(HttpStatus.CREATED)" in ctrl
    assert "@ResponseStatus(HttpStatus.NO_CONTENT)" in ctrl


def test_service_validates_required_fields_and_references(project):
    svc = _java(project, "services/PedidoService.java")
    assert "El campo 'fecha' es obligatorio" in svc
    assert "new NotFoundException(" in svc
    assert "clienteId: no existe Cliente con id" in svc
    # Los metodos sobre la entidad que usa el dispatcher UAP siguen estando.
    for method in ("public List<Pedido> findAll()", "public Optional<Pedido> findById(Long id)",
                   "public Pedido save(Pedido entity)", "public void delete(Long id)"):
        assert method in svc


def test_exception_handler_maps_errors_to_http_status(project):
    handler = _java(project, "exceptions/ApiExceptionHandler.java")
    for status in ("NOT_FOUND", "BAD_REQUEST", "CONFLICT"):
        assert f"HttpStatus.{status}" in handler


def test_jackson_config_keeps_spring_boot_modules(project):
    # Un `new ObjectMapper()` @Primary pisaba al de Spring Boot y perdia el
    # soporte de LocalDate/Optional (500 al crear, GET /{id} roto).
    cfg = _java(project, "uap/JacksonTimeZoneConfig.java")
    code = "\n".join(l for l in cfg.splitlines() if not l.strip().startswith(("*", "/*", "//")))
    assert "new ObjectMapper()" not in code
    assert "@Primary" not in code
    assert "Jackson2ObjectMapperBuilderCustomizer" in code


def test_application_properties_keeps_data_and_reads_credentials_from_env(project):
    props = (project / "src" / "main" / "resources" / "application.properties").read_text(encoding="utf-8")
    assert "ddl-auto=${DDL_AUTO:update}" in props  # "create" borraba la base en cada arranque
    assert "${DB_USER:" in props and "${DB_PASSWORD:" in props
    assert "BasicBinder=TRACE" not in props  # volcaba los valores de cada consulta al log


def test_docker_compose_reads_credentials_from_env(project):
    compose = (project / "docker-compose.yml").read_text(encoding="utf-8")
    assert "POSTGRES_PASSWORD: ${DB_PASSWORD:-" in compose
    assert "DB_PASSWORD: ${DB_PASSWORD:-" in compose


def test_postman_bodies_match_the_dto(project):
    collection = json.loads((project / "postman_collection.json").read_text(encoding="utf-8"))
    pedido = next(f for f in collection["item"] if f["name"].startswith("Pedido"))
    create = next(i for i in pedido["item"] if i["name"].startswith("Create"))
    body = json.loads(create["request"]["body"]["raw"])
    assert body["clienteId"] == 1
    assert any(k.endswith("Ids") and v == [1] for k, v in body.items())
    assert "cliente" not in body and "productos" not in body


def test_uap_idempotency_survives_restarts(project):
    # Antes era un mapa en memoria: reenviar una operacion offline despues
    # de reiniciar el backend creaba un duplicado.
    dispatcher = _java(project, "uap/UapToolDispatcher.java")
    changelog = _java(project, "uap/UapChangeLog.java")
    assert 'name = "client_record_id", unique = true' in changelog
    assert "where c.clientRecordId = :id" in dispatcher
    assert '"CREATE", clientRecordId)' in dispatcher


def test_inverse_side_relations_are_read_only(diagram_tienda_path):
    models = {m["class_name"]: m for m in build_api_models(diagram_tienda_path)}
    cliente = models["Cliente"]
    inverse = [r for r in cliente["rels"] if not r["owner"]]
    assert inverse, "Cliente deberia tener la lista de pedidos del lado inverso"
    assert all(r not in cliente["owner_rels"] for r in inverse)
