from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user, get_spi_service
from app.schemas.auth import UserRead
from app.schemas.spi import SpiTaskCreate, SpiTaskRead
from app.services.spi_service import SpiService


router = APIRouter(prefix="/spi")


@router.post("/tasks", response_model=SpiTaskRead)
def create_spi_task(
    payload: SpiTaskCreate,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    spi_service: Annotated[SpiService, Depends(get_spi_service)],
) -> SpiTaskRead:
    return spi_service.create_task(current_user.username, payload.file_ids or [payload.file_id])


@router.get("/tasks/{task_id}", response_model=SpiTaskRead)
def get_spi_task(
    task_id: str,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    spi_service: Annotated[SpiService, Depends(get_spi_service)],
) -> SpiTaskRead:
    return spi_service.get_task(current_user.username, task_id)
