from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_code_operation_service, get_current_user
from app.schemas.auth import UserRead
from app.schemas.code_operations import CodeAuditListResponse, CodeOperationListResponse, CodeOperationRead
from app.services.code_operation_service import CodeOperationService


router = APIRouter(prefix="/code-operations")


@router.get("", response_model=CodeOperationListResponse)
def list_code_operations(
    current_user: Annotated[UserRead, Depends(get_current_user)],
    operation_service: Annotated[CodeOperationService, Depends(get_code_operation_service)],
    conversation_id: str | None = None,
    operation_status: str | None = Query(default=None, alias="status"),
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> CodeOperationListResponse:
    return CodeOperationListResponse(
        items=operation_service.list_operations(
            current_user.username,
            conversation_id=conversation_id,
            operation_status=operation_status,
            limit=limit,
        )
    )


@router.get("/audit", response_model=CodeAuditListResponse)
def list_code_audit_records(
    current_user: Annotated[UserRead, Depends(get_current_user)],
    operation_service: Annotated[CodeOperationService, Depends(get_code_operation_service)],
    conversation_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> CodeAuditListResponse:
    """查询当前用户的 code agent 操作审计记录。"""
    return CodeAuditListResponse(
        items=operation_service.list_audit_records(
            current_user.username,
            conversation_id=conversation_id,
            limit=limit,
        )
    )


@router.get("/{operation_id}", response_model=CodeOperationRead)
def get_code_operation(
    operation_id: str,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    operation_service: Annotated[CodeOperationService, Depends(get_code_operation_service)],
) -> CodeOperationRead:
    return operation_service.get_operation(current_user.username, operation_id)


@router.post("/{operation_id}/confirm", response_model=CodeOperationRead)
def confirm_code_operation(
    operation_id: str,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    operation_service: Annotated[CodeOperationService, Depends(get_code_operation_service)],
) -> CodeOperationRead:
    return operation_service.confirm_operation(current_user.username, operation_id)


@router.post("/{operation_id}/cancel", response_model=CodeOperationRead)
def cancel_code_operation(
    operation_id: str,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    operation_service: Annotated[CodeOperationService, Depends(get_code_operation_service)],
) -> CodeOperationRead:
    return operation_service.cancel_operation(current_user.username, operation_id)
