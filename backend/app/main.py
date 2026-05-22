from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.services.task_executor import create_task_executor


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """应用生命周期钩子。

    后端所有耗时业务任务都会通过 task_executor 提交。这里在应用启动时
    创建执行器，并在服务退出时统一 shutdown，避免线程池或后台任务悬挂。
    """
    settings = get_settings()
    executor = create_task_executor(settings.task_executor, settings.task_executor_max_workers)
    app.state.task_executor = executor
    try:
        yield
    finally:
        shutdown = getattr(executor, "shutdown", None)
        if shutdown is not None:
            shutdown(wait=True)


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。

    这个函数集中完成配置读取、CORS 注册和 v1 API 路由挂载。测试中也可以
    直接调用它得到一个干净的 app，避免依赖全局副作用。
    """
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=getattr(settings, "cors_origin_regex", None),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
