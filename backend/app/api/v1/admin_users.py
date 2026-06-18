from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.dependencies import get_current_admin, get_user_admin_service
from app.schemas.auth import (
    AdminUserCreateRequest,
    AdminUserListResponse,
    AdminUserRead,
    UserRead,
)
from app.services.user_admin_service import UserAdminService


router = APIRouter(prefix="/admin/users")


@router.get("", response_model=AdminUserListResponse)
def list_users(
    _admin: Annotated[UserRead, Depends(get_current_admin)],
    service: Annotated[UserAdminService, Depends(get_user_admin_service)],
) -> AdminUserListResponse:
    return AdminUserListResponse(items=service.list_users())


@router.post("", response_model=AdminUserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: AdminUserCreateRequest,
    _admin: Annotated[UserRead, Depends(get_current_admin)],
    service: Annotated[UserAdminService, Depends(get_user_admin_service)],
) -> AdminUserRead:
    return service.create_user(payload.username, payload.password, is_admin=payload.is_admin)


@router.delete("/{username}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    username: str,
    admin: Annotated[UserRead, Depends(get_current_admin)],
    service: Annotated[UserAdminService, Depends(get_user_admin_service)],
) -> Response:
    service.delete_user(username, acting_username=admin.username)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
