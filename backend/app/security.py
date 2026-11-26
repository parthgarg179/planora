"""Password hashing (bcrypt) and login tokens (JWT)."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    # bcrypt only uses the first 72 bytes
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:72], hashed.encode())
    except ValueError:
        return False


def create_token(user_id: int) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.token_expire_minutes)
    return jwt.encode({"sub": str(user_id), "exp": expires}, settings.secret_key, algorithm=ALGORITHM)


def read_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
