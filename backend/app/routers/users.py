from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import current_user
from ..models import User
from ..ml.predictor import estimates_status
from ..schemas import EstimatesOut, PasswordChange, UserOut, UserUpdate
from ..security import hash_password, verify_password
from ..serializers import user_out

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user_out(user)


@router.get("/me/estimates", response_model=EstimatesOut)
def my_estimates(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Are this user's task estimates from the AI or personalised? (Only ever about the logged-in user.)"""
    return estimates_status(db, user.id)


@router.patch("/me", response_model=UserOut)
def update_me(body: UserUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes:
        if changes["name"] is None or not changes["name"].strip():
            raise HTTPException(400, "Name can’t be empty.")
        user.name = changes["name"].strip()
    if "email" in changes:
        if changes["email"] is None:
            raise HTTPException(400, "Email can’t be empty.")
        email = changes["email"].lower()
        if email != user.email and db.scalar(select(User).where(User.email == email)):
            raise HTTPException(status.HTTP_409_CONFLICT, "Another account already uses this email.")
        user.email = email
    if "photo_url" in changes:
        user.photo_url = changes["photo_url"]  # None removes the photo
    db.commit()
    return user_out(user)


@router.post("/me/password", status_code=204)
def change_password(body: PasswordChange, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Your current password is incorrect.")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return None
