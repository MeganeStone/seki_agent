from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user, get_diff_service
from app.schemas.auth import UserRead
from app.schemas.diff import DiffTaskCreate, DiffTaskRead
from app.services.diff_service import DiffService


router = APIRouter(prefix="/diff")


@router.post("/tasks", response_model=DiffTaskRead)
def create_diff_task(
    payload: DiffTaskCreate,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    diff_service: Annotated[DiffService, Depends(get_diff_service)],
) -> DiffTaskRead:
    return diff_service.create_task(current_user.username, payload.left_file_id, payload.right_file_id)


@router.get("/tasks/{task_id}", response_model=DiffTaskRead)
def get_diff_task(
    task_id: str,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    diff_service: Annotated[DiffService, Depends(get_diff_service)],
) -> DiffTaskRead:
    return diff_service.get_task(current_user.username, task_id)

