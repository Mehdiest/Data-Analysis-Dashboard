"""
auth.py — JWT token creation and FastAPI dependency for protected routes.

Design decisions:
  - Single demo user (no users table) keeps the portfolio project lean.
  - Credentials are validated against settings; in production these would
    be hashed rows in a users table.
  - Every protected route receives the decoded payload via get_current_user().
"""

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

# ── Password hashing ───────────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── Bearer token extractor ─────────────────────────────────────────────────────
bearer_scheme = HTTPBearer()


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def authenticate_user(username: str, password: str) -> bool:
    """
    Validate credentials against the demo account stored in settings.
    Returns True on success, False on any mismatch.
    """
    if username != settings.demo_username:
        return False
    # For a real app: fetch the user row and call verify_password(password, user.hashed_password)
    if password != settings.demo_password:
        return False
    return True


def create_access_token(data: dict) -> str:
    """
    Encode a JWT with an expiry claim.
    `data` should contain at least {"sub": username}.
    """
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload.update({"exp": expire})
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> str:
    """
    FastAPI dependency — decode and validate the Bearer JWT.
    Returns the `sub` claim (username) on success.
    Raises HTTP 401 on any failure.
    """
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    return username
