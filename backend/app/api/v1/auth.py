from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_auth_service, get_current_user
from app.schemas.auth import LoginRequest, LoginResponse, UserRead
from app.services.auth_service import AuthService


router = APIRouter(prefix="/auth")


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> LoginResponse:
    result = auth_service.authenticate(payload.username, payload.password)
    if result is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    return result


@router.get("/me", response_model=UserRead)
def me(current_user: Annotated[UserRead, Depends(get_current_user)]) -> UserRead:
    return current_user

