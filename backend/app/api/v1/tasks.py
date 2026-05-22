from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_current_user, get_task_service
from app.schemas.auth import UserRead
from app.schemas.tasks import TaskListResponse, TaskRead
from app.services.task_service import TaskService


router = APIRouter(prefix="/tasks")


@router.get("", response_model=TaskListResponse)
def list_tasks(
    current_user: Annotated[UserRead, Depends(get_current_user)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> TaskListResponse:
    return task_service.list_tasks(current_user.username, limit=limit)


@router.get("/{task_id}", response_model=TaskRead)
def get_task(
    task_id: str,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
) -> TaskRead:
    return task_service.get_task(current_user.username, task_id)


@router.post("/{task_id}/cancel", response_model=TaskRead)
def cancel_task(
    task_id: str,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
) -> TaskRead:
    return task_service.cancel_task(current_user.username, task_id)
