
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.schemas.auth import SignInIn, TokensOut
from app.models.user import User
from app.core.security import verify_password, create_access_token

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
