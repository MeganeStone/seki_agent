from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
import logging
from typing import Protocol


TaskFn = Callable[[], None]
logger = logging.getLogger(__name__)


class TaskExecutor(Protocol):
    def submit(self, task: TaskFn) -> None:
        """提交一个无返回值任务。"""


class SynchronousTaskExecutor:
    """同步执行器。

    测试和本地调试时很有用：提交任务后立即执行，断言结果不需要等待线程调度。
    """

    def submit(self, task: TaskFn) -> None:
        task()


class ThreadPoolTaskExecutor:
    """单进程 MVP 使用的本地线程池执行器。

    它能让上传接口快速返回 pending/running 任务，但不是分布式队列；生产高可用
    场景后续建议迁移到 Redis + Celery/RQ。
    """

    def __init__(self, max_workers: int = 3) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="seki-task")
        self._futures: set[Future[None]] = set()

    def submit(self, task: TaskFn) -> None:
        future = self._pool.submit(task)
        self._futures.add(future)
        future.add_done_callback(self._on_done)

    def shutdown(self, wait: bool = True) -> None:
        self._pool.shutdown(wait=wait, cancel_futures=False)

    def _on_done(self, future: Future[None]) -> None:
        self._futures.discard(future)
        try:
            future.result()
        except Exception:
            logger.exception("Background task failed with an unhandled exception")


class CeleryTaskExecutor:
    """把业务任务发到 Celery 队列的执行器。

    Celery 任务必须可 JSON 序列化，所以这里不接受闭包；service 层在检测到
    Celery 执行器时改用 enqueue(kind, payload)，由 worker 端的
    dispatch_business_task 重建 service 执行。
    """

    def __init__(self, send_task=None) -> None:
        # send_task 可注入用于测试；默认懒加载 celery 任务避免无 Redis 环境 import 即失败。
        self._send_task = send_task

    def submit(self, task: TaskFn) -> None:
        raise RuntimeError("CeleryTaskExecutor 不支持闭包任务，请使用 enqueue(kind, payload)")

    def enqueue(self, kind: str, payload: dict) -> None:
        if self._send_task is None:
            from app.celery_app import run_business_task

            self._send_task = lambda task_kind, task_payload: run_business_task.delay(task_kind, task_payload)
        self._send_task(kind, payload)


def create_task_executor(kind: str, max_workers: int = 3) -> TaskExecutor:
    """根据配置创建任务执行器。"""
    normalized = kind.strip().lower()
    if normalized in {"sync", "synchronous"}:
        return SynchronousTaskExecutor()
    if normalized in {"thread", "threadpool", "local_thread"}:
        return ThreadPoolTaskExecutor(max_workers=max_workers)
    if normalized == "celery":
        return CeleryTaskExecutor()
    raise ValueError(f"Unsupported task executor: {kind}")
