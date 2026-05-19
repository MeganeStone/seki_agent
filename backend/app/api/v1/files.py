from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import FileResponse

from app.api.dependencies import get_current_user, get_file_service
from app.schemas.auth import UserRead
from app.schemas.files import DeleteFileResponse, FileListResponse, FileRead
from app.services.file_service import FileService


router = APIRouter(prefix="/files")


@router.get("", response_model=FileListResponse)
def list_files(
    current_user: Annotated[UserRead, Depends(get_current_user)],
    file_service: Annotated[FileService, Depends(get_file_service)],
) -> FileListResponse:
    return FileListResponse(items=file_service.list_files(current_user.username))


@router.post("", response_model=FileRead)
async def upload_file(
    file: UploadFile,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    file_service: Annotated[FileService, Depends(get_file_service)],
) -> FileRead:
    return await file_service.save_upload(current_user.username, file)


@router.get("/{file_id}/download")
def download_file(
    file_id: str,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    file_service: Annotated[FileService, Depends(get_file_service)],
) -> FileResponse:
    path, filename = file_service.get_file_path(current_user.username, file_id)
    return FileResponse(path, filename=filename)


@router.delete("/{file_id}", response_model=DeleteFileResponse)
def delete_file(
    file_id: str,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    file_service: Annotated[FileService, Depends(get_file_service)],
) -> DeleteFileResponse:
    return DeleteFileResponse(deleted=file_service.delete_file(current_user.username, file_id))

