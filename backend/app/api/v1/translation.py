from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user, get_translation_service
from app.schemas.auth import UserRead
from app.schemas.translation import TranslationTaskCreate, TranslationTaskRead
from app.services.translation_service import TranslationService


router = APIRouter(prefix="/translation")


@router.post("/tasks", response_model=TranslationTaskRead)
def create_translation_task(
    payload: TranslationTaskCreate,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    translation_service: Annotated[TranslationService, Depends(get_translation_service)],
) -> TranslationTaskRead:
    return translation_service.create_task(
        current_user.username,
        payload.file_id,
        payload.target_language,
        api_key=payload.api_key,
    )


@router.get("/tasks/{task_id}", response_model=TranslationTaskRead)
def get_translation_task(
    task_id: str,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    translation_service: Annotated[TranslationService, Depends(get_translation_service)],
) -> TranslationTaskRead:
    return translation_service.get_task(current_user.username, task_id)
