"""命名业务任务的统一分发入口。

Celery worker（或其他只能传 JSON 参数的执行器）通过 kind + payload 描述任务，
由这里重建数据库连接和对应 service 后执行。线程池/同步执行器仍然走闭包路径，
不经过本模块。
"""
from app.db.postgres import connect
from app.services.task_executor import SynchronousTaskExecutor


def dispatch_business_task(kind: str, payload: dict) -> None:
    conn = connect()
    try:
        if kind == "translation":
            from app.services.translation_service import TranslationService

            TranslationService(conn, task_executor=SynchronousTaskExecutor())._run_task(
                str(payload["task_id"]),
                str(payload["owner_username"]),
                str(payload["file_id"]),
                str(payload["target_language"]),
                api_key=payload.get("api_key"),
            )
            return
        if kind == "spi":
            from app.services.spi_service import SpiService

            SpiService(conn, task_executor=SynchronousTaskExecutor())._run_task(
                str(payload["task_id"]),
                str(payload["owner_username"]),
                [str(file_id) for file_id in payload["file_ids"]],
            )
            return
        if kind == "diff":
            from app.services.diff_service import DiffService

            DiffService(conn, task_executor=SynchronousTaskExecutor())._run_task(
                str(payload["task_id"]),
                str(payload["owner_username"]),
                str(payload["left_file_id"]),
                str(payload["right_file_id"]),
            )
            return
        raise ValueError(f"Unknown business task kind: {kind}")
    finally:
        conn.close()
