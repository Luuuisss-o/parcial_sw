from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from passlib.hash import bcrypt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.models.user import User

bearer = HTTPBearer(auto_error=False)

# ========================
# Password helpers
# ========================

def hash_password(password: str) -> str:
    return bcrypt.hash(password[:72])   # corta a 72 chars

def verify_password(raw: str, hashed: str) -> bool:
    return bcrypt.verify(raw[:72], hashed)


# ========================
# JWT helpers
# ========================
def create_access_token(sub: str) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.ACCESS_EXPIRE_MIN)
    payload = {
        "sub": sub,
        "kind": "access",
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)

def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])

# ========================
# Auth dependency
# ========================
def get_current_user(
    cred: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    """
    Devuelve el usuario actual basado en el token JWT.
    """

    if cred is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization",
        )

    try:
        payload = decode_token(cred.credentials)
        if payload.get("kind") != "access":
            raise HTTPException(status_code=401, detail="Invalid token kind")
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token payload")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = db.query(User).filter(User.email == email).one_or_none()
    if not user or not user.active:
        raise HTTPException(status_code=401, detail="User disabled")

    return user
