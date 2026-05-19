import sqlite3
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_access_token
from app.db.sqlite import get_connection
from app.schemas.auth import UserRead
from app.services.agent_service import AgentService
from app.services.auth_service import AuthService
from app.services.diff_service import DiffService
from app.services.file_service import FileService
from app.services.rag_service import RagService
from app.services.spi_service import SpiService
from app.services.translation_service import TranslationService


bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_service(conn: Annotated[sqlite3.Connection, Depends(get_connection)]) -> AuthService:
    return AuthService(conn)


def get_file_service(conn: Annotated[sqlite3.Connection, Depends(get_connection)]) -> FileService:
    return FileService(conn)


def get_diff_service(conn: Annotated[sqlite3.Connection, Depends(get_connection)]) -> DiffService:
    return DiffService(conn)


def get_spi_service(conn: Annotated[sqlite3.Connection, Depends(get_connection)]) -> SpiService:
    return SpiService(conn)


def get_translation_service(conn: Annotated[sqlite3.Connection, Depends(get_connection)]) -> TranslationService:
    return TranslationService(conn)


def get_rag_service() -> RagService:
    return RagService()


def get_agent_service(
    conn: Annotated[sqlite3.Connection, Depends(get_connection)],
    rag_service: Annotated[RagService, Depends(get_rag_service)],
    file_service: Annotated[FileService, Depends(get_file_service)],
    translation_service: Annotated[TranslationService, Depends(get_translation_service)],
    spi_service: Annotated[SpiService, Depends(get_spi_service)],
    diff_service: Annotated[DiffService, Depends(get_diff_service)],
) -> AgentService:
    return AgentService(
        conn,
        rag_service=rag_service,
        file_service=file_service,
        translation_service=translation_service,
        spi_service=spi_service,
        diff_service=diff_service,
    )


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> UserRead:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = auth_service.get_user(payload["sub"])
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
