
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.db import get_db
from app.schemas.auth import SignInIn, SignUpRequest, TokensOut
from app.models.user import User, Role
from app.core.security import verify_password, create_access_token, hash_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# POST
# http://localhost:8000/auth/sign-in
# {
#   "email": "admin@example.com",
#   "password": "changeme123"
# }

@router.post("/sign-in", response_model=TokensOut)
def sign_in(body: SignInIn, db: Session = Depends(get_db)):
    email = body.email.lower().strip()
    user = db.query(User).filter(User.email == email).one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Credenciales inválidas")
    token = create_access_token(sub=email)
    return TokensOut(access_token=token)


# ---------------------------------------------------------------------------
# Registro de usuarios
# ---------------------------------------------------------------------------
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# POST /auth/sign-up  {"name": "Ana Pérez", "email": "ana@mail.com", "password": "********"}
@router.post("/sign-up", response_model=TokensOut, status_code=status.HTTP_201_CREATED)
def sign_up(body: SignUpRequest, db: Session = Depends(get_db)):
    """Crea una cuenta nueva (rol editor, como los integrantes de un equipo)
    y devuelve el token: el usuario queda con la sesión iniciada.

    Los errores vienen en español y uno por vez, para mostrarlos tal cual en
    el formulario (la validación de Pydantic los daría en inglés)."""
    name = " ".join(body.name.split())
    email = body.email.strip().lower()
    password = body.password

    if len(name) < 2:
        raise HTTPException(400, "Ingresá tu nombre (al menos 2 letras).")
    if len(name) > 120:
        raise HTTPException(400, "El nombre es demasiado largo (máximo 120 caracteres).")
    if len(email) > 160 or not _EMAIL_RE.match(email):
        raise HTTPException(400, "Ingresá un correo electrónico válido.")
    if len(password) < 8:
        raise HTTPException(400, "La contraseña tiene que tener al menos 8 caracteres.")
    if len(password) > 128:
        raise HTTPException(400, "La contraseña es demasiado larga (máximo 128 caracteres).")
    if password.strip() != password or not password.strip():
        raise HTTPException(400, "La contraseña no puede empezar ni terminar con espacios.")

    if db.query(User).filter(func.lower(User.email) == email).first():
        raise HTTPException(409, "Ya existe una cuenta con ese correo. Iniciá sesión.")

    user = User(name=name, email=email, password_hash=hash_password(password), role=Role.editor)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Otra alta con el mismo correo ganó la carrera (índice único en la base).
        db.rollback()
        raise HTTPException(409, "Ya existe una cuenta con ese correo. Iniciá sesión.")

    logger.info(f"[AUTH] cuenta nueva user_id={user.id}")
    return TokensOut(access_token=create_access_token(sub=email))
