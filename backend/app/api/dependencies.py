import psycopg
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.context import current_user_var
from app.core.security import decode_access_token
from app.db.postgres import get_connection
from app.schemas.auth import UserRead
from app.services.agent_service import AgentService
from app.services.auth_service import AuthService
from app.services.code_operation_service import CodeOperationService
from app.services.diff_service import DiffService
from app.services.file_service import FileService
from app.services.rag_service import RagService
from app.services.spi_service import SpiService
from app.services.task_executor import SynchronousTaskExecutor, TaskExecutor
from app.services.task_service import TaskService
from app.services.translation_service import TranslationService
from app.services.user_admin_service import UserAdminService


bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_service(conn: Annotated[psycopg.Connection, Depends(get_connection)]) -> AuthService:
    """创建认证服务；每个请求复用同一个 postgresql 连接依赖。"""
    return AuthService(conn)


def get_file_service(conn: Annotated[psycopg.Connection, Depends(get_connection)]) -> FileService:
    return FileService(conn)


def get_task_service(conn: Annotated[psycopg.Connection, Depends(get_connection)]) -> TaskService:
    return TaskService(conn)


def get_code_operation_service(
    conn: Annotated[psycopg.Connection, Depends(get_connection)],
    file_service: Annotated[FileService, Depends(get_file_service)],
) -> CodeOperationService:
    return CodeOperationService(conn, file_service=file_service)


def get_task_executor(request: Request) -> TaskExecutor:
    """从 FastAPI app.state 读取后台任务执行器。

    lifespan 启动失败或测试未挂载 lifespan 时，降级到同步执行器，保证业务
    service 仍能被单元测试直接调用。
    """
    return getattr(request.app.state, "task_executor", SynchronousTaskExecutor())


def get_diff_service(
    conn: Annotated[psycopg.Connection, Depends(get_connection)],
    task_executor: Annotated[TaskExecutor, Depends(get_task_executor)],
) -> DiffService:
    return DiffService(conn, task_executor=task_executor)


def get_spi_service(
    conn: Annotated[psycopg.Connection, Depends(get_connection)],
    task_executor: Annotated[TaskExecutor, Depends(get_task_executor)],
) -> SpiService:
    return SpiService(conn, task_executor=task_executor)


def get_translation_service(
    conn: Annotated[psycopg.Connection, Depends(get_connection)],
    task_executor: Annotated[TaskExecutor, Depends(get_task_executor)],
) -> TranslationService:
    return TranslationService(conn, task_executor=task_executor)


def get_rag_service() -> RagService:
    return RagService()


def get_agent_service(
    conn: Annotated[psycopg.Connection, Depends(get_connection)],
    rag_service: Annotated[RagService, Depends(get_rag_service)],
    file_service: Annotated[FileService, Depends(get_file_service)],
    translation_service: Annotated[TranslationService, Depends(get_translation_service)],
    spi_service: Annotated[SpiService, Depends(get_spi_service)],
    diff_service: Annotated[DiffService, Depends(get_diff_service)],
) -> AgentService:
    """组装 AgentService 依赖。

    Chat API 不直接知道 RAG、翻译、SPI、diff 的实现细节，而是通过这里把
    各 service 注入给 AgentService，再由 LangGraph runner 决定是否调用工具。
    """
    return AgentService(
        conn,
        rag_service=rag_service,
        file_service=file_service,
        translation_service=translation_service,
        spi_service=spi_service,
        diff_service=diff_service,
    )


def get_user_admin_service(
    conn: Annotated[psycopg.Connection, Depends(get_connection)],
) -> UserAdminService:
    return UserAdminService(conn)


def get_agent_trace_service(
    conn: Annotated[psycopg.Connection, Depends(get_connection)],
) -> "AgentTraceService":
    from app.services.agent_trace_service import AgentTraceService

    return AgentTraceService(conn)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> UserRead:
    """解析 Bearer Token 并返回当前登录用户。

    这里是所有需要登录接口的统一鉴权入口：缺 token、token 无效、用户不存在
    都返回 401，业务接口无需重复处理认证细节。
    """
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = auth_service.get_user(payload["sub"])
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    current_user_var.set(user.username)
    return user


def get_current_admin(
    current_user: Annotated[UserRead, Depends(get_current_user)],
) -> UserRead:
    """要求当前用户是管理员，否则 403。"""
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return current_user
