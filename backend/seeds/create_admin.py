# seeds/create_admin.py
"""
Crea (o promueve) un usuario administrador SIN cargar los datos demo, cuyas
contraseñas son públicas (admin123). Pensado para producción:

    docker compose -f docker-compose.prod.yml exec backend \
        python -m seeds.create_admin tu@email.com "Tu Nombre"

Pide la contraseña por teclado (o la toma de ADMIN_PASSWORD). El rol admin
es el que permite publicar el modelo personalizado (PUT /models/assistant).
"""
from __future__ import annotations

import getpass
import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from passlib.hash import bcrypt  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models.user import Role, User  # noqa: E402

MIN_PASSWORD = 8


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Uso: python -m seeds.create_admin EMAIL [NOMBRE]")
        return 2
    email = argv[1].strip().lower()
    name = argv[2].strip() if len(argv) > 2 else email.split("@")[0]
    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Contraseña nueva: ")
    if len(password) < MIN_PASSWORD:
        print(f"La contraseña debe tener al menos {MIN_PASSWORD} caracteres")
        return 1

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).one_or_none()
        if user:
            user.role = Role.admin
            user.active = True
            user.password_hash = bcrypt.hash(password)
            action = "promovido a admin (contraseña actualizada)"
        else:
            db.add(User(email=email, name=name, password_hash=bcrypt.hash(password), role=Role.admin, active=True))
            action = "creado como admin"
        db.commit()
    print(f"{email}: {action}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
