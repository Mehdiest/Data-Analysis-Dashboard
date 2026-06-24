"""
routers/auth.py — Login endpoint that issues JWT bearer tokens.
"""

from fastapi import APIRouter, HTTPException, status

from app.auth import authenticate_user, create_access_token
from app.schemas import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse, summary="Obtain a JWT access token")
def login(body: LoginRequest):
    """
    Validate credentials and return a signed JWT.

    The token must be sent as `Authorization: Bearer <token>` on all
    subsequent requests to protected endpoints.
    """
    if not authenticate_user(body.username, body.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    token = create_access_token({"sub": body.username})
    return TokenResponse(access_token=token)
