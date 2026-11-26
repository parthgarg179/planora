from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import LoginIn, SignupIn, TokenOut
from ..security import create_token, hash_password, verify_password
from ..serializers import user_out

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenOut, status_code=201)
def signup(body: SignupIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    user = User(name=body.name.strip(), email=email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    return {"token": create_token(user.id), "user": user_out(user)}


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    return {"token": create_token(user.id), "user": user_out(user)}


@router.post("/logout", status_code=204)
def logout():
    # Tokens are stateless; the frontend forgets its token. (Add a token blocklist if you need server-side logout.)
    return None
