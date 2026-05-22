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


def create_task_executor(kind: str, max_workers: int = 3) -> TaskExecutor:
    """根据配置创建任务执行器。"""
    normalized = kind.strip().lower()
    if normalized in {"sync", "synchronous"}:
        return SynchronousTaskExecutor()
    if normalized in {"thread", "threadpool", "local_thread"}:
        return ThreadPoolTaskExecutor(max_workers=max_workers)
    raise ValueError(f"Unsupported task executor: {kind}")
