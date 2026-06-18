"""Celery 应用与任务注册。

Worker 启动方式（Windows 本机需用 solo/threads pool）：

    celery -A app.celery_app.celery_app worker --pool=solo -l info

Docker Compose 中由 worker 服务启动。
"""
from celery import Celery

from app.core.config import get_settings
from app.core.logging import configure_logging


def create_celery_app() -> Celery:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format, settings.log_dir)
    app = Celery("seki_agent", broker=settings.celery_broker_url)
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        task_default_queue="seki-tasks",
        # 任务结果都写业务库，不需要 result backend。
        task_ignore_result=True,
        task_always_eager=settings.celery_task_always_eager,
        broker_connection_retry_on_startup=True,
    )
    return app


celery_app = create_celery_app()


@celery_app.task(name="seki.run_business_task")
def run_business_task(kind: str, payload: dict) -> None:
    from app.services.business_tasks import dispatch_business_task

    dispatch_business_task(kind, payload)
