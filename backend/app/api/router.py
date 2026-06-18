from fastapi import APIRouter

from app.api.v1.admin_users import router as admin_users_router
from app.api.v1.agent_trace import router as agent_trace_router
from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.code_operations import router as code_operations_router
from app.api.v1.diff import router as diff_router
from app.api.v1.files import router as files_router
from app.api.v1.health import router as health_router
from app.api.v1.spi import router as spi_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.translation import router as translation_router


api_router = APIRouter()
api_router.include_router(auth_router, tags=["auth"])
api_router.include_router(admin_users_router, tags=["admin"])
api_router.include_router(agent_trace_router, tags=["agent-trace"])
api_router.include_router(chat_router, tags=["chat"])
api_router.include_router(code_operations_router, tags=["code-operations"])
api_router.include_router(files_router, tags=["files"])
api_router.include_router(diff_router, tags=["diff"])
api_router.include_router(spi_router, tags=["spi"])
api_router.include_router(tasks_router, tags=["tasks"])
api_router.include_router(translation_router, tags=["translation"])
api_router.include_router(health_router, tags=["health"])
