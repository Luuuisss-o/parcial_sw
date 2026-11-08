# seeds/load_csv_sa.py
from __future__ import annotations
import os
import sys
import csv
import uuid
from typing import Optional

# --- Agregar backend al sys.path para importar app.* ---
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.db import SessionLocal
from app.models.user import User  # tu modelo User (role=str o Enum-compatible con 'admin','editor','viewer')
from app.models.uml import Diagram, Clase, Atributo, Metodo, Relacion, RelType
from passlib.hash import bcrypt

DATA_DIR = os.path.join(BASE_DIR, "seeds", "data")

# ---------- Helpers ----------

def bool_from_csv(v: str | None, default: bool=False) -> bool:
    if v is None:
        return default
    return str(v).strip().lower() in ("true", "1", "yes", "y", "si", "sí")

def norm(s: str) -> str:
    return (s or "").strip()

def gen_uuid(s: str | None) -> uuid.UUID:
    return uuid.UUID(s) if s else uuid.uuid4()

def _csv_open(path: str) -> Optional[csv.DictReader]:
    if not os.path.exists(path):
        print(f"[skip] No existe CSV: {path}")
        return None
    f = open(path, newline="", encoding="utf-8")
    return csv.DictReader(f)

# ---------- Loaders ----------

def load_users(db) -> None:
    """
    users.csv: email,name,password,role,active
    - Upsert por email (case-insensitive)
    - password se hashea con bcrypt
    """
    path = os.path.join(DATA_DIR, "users.csv")
    rdr = _csv_open(path)
    if rdr is None:
        return

    created, updated = 0, 0
    for row in rdr:
        email = norm(row.get("email")).lower()
        name = norm(row.get("name"))
        password = norm(row.get("password")) or "changeme123"
        role = norm(row.get("role")) or "editor"
        active = bool_from_csv(row.get("active"), True)

        if not email:
            print(f"[users] fila sin email -> skip")
            continue

        user = db.query(User).filter(User.email == email).one_or_none()
        if user:
            changed = False
            if user.name != name and name:
                user.name = name
                changed = True
            if user.role != role and role:
                user.role = role
                changed = True
            if user.active != active:
                user.active = active
                changed = True
            # Si quieres, re-hashear password si viene distinta (cuidado en prod)
            if password:
                user.password_hash = bcrypt.hash(password)
                changed = True
            if changed:
                updated += 1
                print(f"[users] ↺ actualizado: {email}")
            else:
                print(f"[users] = sin cambios: {email}")
        else:
            user = User(
                email=email,
                name=name or email.split("@")[0],
                password_hash=bcrypt.hash(password),
                role=role,
                active=active,
            )
            db.add(user)
            created += 1
            print(f"[users] + creado: {email}")

    print(f"[users] creado={created}, actualizado={updated}")


def load_diagrams(db) -> None:
    """
    diagrams.csv: id,title,owner_email
    - Upsert por title (único por proyecto)
    - Resuelve owner_id por email
    """
    path = os.path.join(DATA_DIR, "diagrams.csv")
    rdr = _csv_open(path)
    if rdr is None:
        return

    created, updated = 0, 0
    for row in rdr:
        id_raw = norm(row.get("id"))
        title = norm(row.get("title"))
        owner_email = norm(row.get("owner_email")).lower()

        if not title or not owner_email:
            print(f"[diagrams] fila inválida -> skip (title/owner_email requeridos)")
            continue

        owner = db.query(User).filter(User.email == owner_email).one_or_none()
        if not owner:
            print(f"[diagrams] ! owner no encontrado: {owner_email} -> skip")
            continue

        # upsert por title
        diagram = db.query(Diagram).filter(Diagram.title == title).one_or_none()
        if diagram:
            changed = False
            if diagram.owner_id != owner.id:
                diagram.owner_id = owner.id
                changed = True
            if changed:
                updated += 1
                print(f"[diagrams] ↺ actualizado: {title}")
            else:
                print(f"[diagrams] = sin cambios: {title}")
        else:
            diagram = Diagram(
                id=gen_uuid(id_raw),
                title=title,
                owner_id=owner.id,
            )
            db.add(diagram)
            created += 1
            print(f"[diagrams] + creado: {title}")

    print(f"[diagrams] creado={created}, actualizado={updated}")


def load_clases(db) -> None:
    """
    clases.csv: id,diagram_title,nombre
    - Upsert por (diagram_id, nombre) (tienes unique en migración)
    """
    path = os.path.join(DATA_DIR, "clases.csv")
    rdr = _csv_open(path)
    if rdr is None:
        return

    created, updated = 0, 0
    for row in rdr:
        id_raw = norm(row.get("id"))
        diagram_title = norm(row.get("diagram_title"))
        nombre = norm(row.get("nombre"))

        if not diagram_title or not nombre:
            print(f"[clases] fila inválida -> skip (diagram_title/nombre requeridos)")
            continue

        diagram = db.query(Diagram).filter(Diagram.title == diagram_title).one_or_none()
        if not diagram:
            print(f"[clases] ! diagrama no encontrado: {diagram_title} -> skip")
            continue

        clase = (
            db.query(Clase)
            .filter(Clase.diagram_id == diagram.id, Clase.nombre == nombre)
            .one_or_none()
        )
        if clase:
            print(f"[clases] = sin cambios: {diagram_title}.{nombre}")
            updated += 1  # lo contamos como “visitado”
        else:
            clase = Clase(
                id=gen_uuid(id_raw),
                nombre=nombre,
                diagram_id=diagram.id,
            )
            db.add(clase)
            created += 1
            print(f"[clases] + creada: {diagram_title}.{nombre}")

    print(f"[clases] creado={created}, existente={updated}")


def load_atributos(db) -> None:
    """
    atributos.csv: diagram_title,clase_nombre,nombre,tipo,requerido
    - Upsert por (clase_id, nombre)
    """
    path = os.path.join(DATA_DIR, "atributos.csv")
    rdr = _csv_open(path)
    if rdr is None:
        return

    created, updated = 0, 0
    for row in rdr:
        diagram_title = norm(row.get("diagram_title"))
        clase_nombre = norm(row.get("clase_nombre"))
        nombre = norm(row.get("nombre"))
        tipo = norm(row.get("tipo")) or "string"
        requerido = bool_from_csv(row.get("requerido"), False)

        if not (diagram_title and clase_nombre and nombre):
            print(f"[attrs] fila inválida -> skip (diagram_title, clase_nombre, nombre)")
            continue

        diagram = db.query(Diagram).filter(Diagram.title == diagram_title).one_or_none()
        if not diagram:
            print(f"[attrs] ! diagrama no encontrado: {diagram_title} -> skip")
            continue

        clase = (
            db.query(Clase)
            .filter(Clase.diagram_id == diagram.id, Clase.nombre == clase_nombre)
            .one_or_none()
        )
        if not clase:
            print(f"[attrs] ! clase no encontrada: {diagram_title}.{clase_nombre} -> skip")
            continue

        attr = (
            db.query(Atributo)
            .filter(Atributo.clase_id == clase.id, Atributo.nombre == nombre)
            .one_or_none()
        )
        if attr:
            changed = False
            if attr.tipo != tipo:
                attr.tipo = tipo
                changed = True
            if attr.requerido != requerido:
                attr.requerido = requerido
                changed = True

            if changed:
                updated += 1
                print(f"[attrs] ↺ actualizado: {clase_nombre}.{nombre}")
            else:
                print(f"[attrs] = sin cambios: {clase_nombre}.{nombre}")
        else:
            db.add(Atributo(
                clase_id=clase.id,
                nombre=nombre,
                tipo=tipo,
                requerido=requerido,
            ))
            created += 1
            print(f"[attrs] + creado: {clase_nombre}.{nombre}")

    print(f"[attrs] creado={created}, actualizado={updated}")


def load_metodos(db) -> None:
    """
    metodos.csv: diagram_title,clase_nombre,nombre,tipo_retorno
    - Upsert por (clase_id, nombre)
    """
    path = os.path.join(DATA_DIR, "metodos.csv")
    rdr = _csv_open(path)
    if rdr is None:
        return

    created, updated = 0, 0
    for row in rdr:
        diagram_title = norm(row.get("diagram_title"))
        clase_nombre = norm(row.get("clase_nombre"))
        nombre = norm(row.get("nombre"))
        tipo_retorno = norm(row.get("tipo_retorno")) or "void"

        if not (diagram_title and clase_nombre and nombre):
            print(f"[metodos] fila inválida -> skip (diagram_title, clase_nombre, nombre)")
            continue

        diagram = db.query(Diagram).filter(Diagram.title == diagram_title).one_or_none()
        if not diagram:
            print(f"[metodos] ! diagrama no encontrado: {diagram_title} -> skip")
            continue

        clase = (
            db.query(Clase)
            .filter(Clase.diagram_id == diagram.id, Clase.nombre == clase_nombre)
            .one_or_none()
        )
        if not clase:
            print(f"[metodos] ! clase no encontrada: {diagram_title}.{clase_nombre} -> skip")
            continue

        m = (
            db.query(Metodo)
            .filter(Metodo.clase_id == clase.id, Metodo.nombre == nombre)
            .one_or_none()
        )
        if m:
            if m.tipo_retorno != tipo_retorno:
                m.tipo_retorno = tipo_retorno
                updated += 1
                print(f"[metodos] ↺ actualizado: {clase_nombre}.{nombre}")
            else:
                print(f"[metodos] = sin cambios: {clase_nombre}.{nombre}")
        else:
            db.add(Metodo(
                clase_id=clase.id,
                nombre=nombre,
                tipo_retorno=tipo_retorno,
            ))
            created += 1
            print(f"[metodos] + creado: {clase_nombre}.{nombre}")

    print(f"[metodos] creado={created}, actualizado={updated}")


def load_relaciones(db) -> None:
    """
    relaciones.csv: diagram_title,origen_nombre,destino_nombre,tipo,etiqueta
    - Upsert por (diagram_id, origen_id, destino_id, tipo, etiqueta NULL-safe)
    - Valida que origen y destino pertenecen al mismo diagrama
    """
    path = os.path.join(DATA_DIR, "relaciones.csv")
    rdr = _csv_open(path)
    if rdr is None:
        return

    created, updated = 0, 0
    for row in rdr:
        diagram_title = norm(row.get("diagram_title"))
        origen_nombre = norm(row.get("origen_nombre"))
        destino_nombre = norm(row.get("destino_nombre"))
        tipo_raw = norm(row.get("tipo"))
        etiqueta = norm(row.get("etiqueta")) or None

        if not (diagram_title and origen_nombre and destino_nombre and tipo_raw):
            print(f"[rels] fila inválida -> skip (diagram_title, origen_nombre, destino_nombre, tipo)")
            continue

        # Enum RelType (validación)
        try:
            tipo = RelType[tipo_raw] if tipo_raw in RelType.__members__ else RelType(tipo_raw)
        except Exception:
            print(f"[rels] ! tipo inválido '{tipo_raw}' -> skip (usa {list(RelType.__members__.keys())})")
            continue

        diagram = db.query(Diagram).filter(Diagram.title == diagram_title).one_or_none()
        if not diagram:
            print(f"[rels] ! diagrama no encontrado: {diagram_title} -> skip")
            continue

        origen = (
            db.query(Clase)
            .filter(Clase.diagram_id == diagram.id, Clase.nombre == origen_nombre)
            .one_or_none()
        )
        destino = (
            db.query(Clase)
            .filter(Clase.diagram_id == diagram.id, Clase.nombre == destino_nombre)
            .one_or_none()
        )
        if not origen or not destino:
            print(f"[rels] ! clase origen/destino no encontrada en '{diagram_title}' "
                  f"({origen_nombre} -> {bool(origen)}, {destino_nombre} -> {bool(destino)}) -> skip")
            continue

        rel = (
            db.query(Relacion)
            .filter(
                Relacion.diagram_id == diagram.id,
                Relacion.origen_id == origen.id,
                Relacion.destino_id == destino.id,
                Relacion.tipo == tipo,
                Relacion.etiqueta.is_(None) if etiqueta is None else Relacion.etiqueta == etiqueta,
            )
            .one_or_none()
        )
        if rel:
            print(f"[rels] = sin cambios: {origen_nombre} -[{tipo.name}/{etiqueta}]-> {destino_nombre}")
            updated += 1
        else:
            db.add(Relacion(
                diagram_id=diagram.id,
                origen_id=origen.id,
                destino_id=destino.id,
                tipo=tipo,
                etiqueta=etiqueta,
            ))
            created += 1
            print(f"[rels] + creada: {origen_nombre} -[{tipo.name}/{etiqueta}]-> {destino_nombre}")

    print(f"[rels] creado={created}, existente={updated}")


# ---------- Runner ----------

def main() -> None:
    # Orden importante: users -> diagrams -> clases -> atributos -> metodos -> relaciones
    db = SessionLocal()
    try:
        print("== Cargando users.csv ==")
        load_users(db); db.commit()

        print("== Cargando diagrams.csv ==")
        load_diagrams(db); db.commit()

        print("== Cargando clases.csv ==")
        load_clases(db); db.commit()

        print("== Cargando atributos.csv ==")
        load_atributos(db); db.commit()

        print("== Cargando metodos.csv ==")
        load_metodos(db); db.commit()

        print("== Cargando relaciones.csv ==")
        load_relaciones(db); db.commit()

        print("✅ Seeds completados.")
    except Exception as e:
        db.rollback()
        print("💥 Error en carga, rollback aplicado.")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    main()


# SELECT * FROM "user";
# SELECT * FROM diagram;
# SELECT * FROM clase;
# SELECT * FROM atributo;
# SELECT * FROM metodo;
# SELECT * FROM relacion;
# SELECT * FROM alembic_version;



# DO $$ DECLARE
#     r RECORD;
# BEGIN
#     -- Desactivar temporalmente restricciones
#     EXECUTE 'SET session_replication_role = replica';

#     -- Eliminar todas las tablas del esquema público
#     FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
#         EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE';
#     END LOOP;

#     -- Restaurar las restricciones
#     EXECUTE 'SET session_replication_role = origin';
# END $$;