from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
import logging
from typing import Protocol


TaskFn = Callable[[], None]
logger = logging.getLogger(__name__)


class TaskExecutor(Protocol):
    def submit(self, task: TaskFn) -> None:
        """Schedule a task for execution."""


class SynchronousTaskExecutor:
    """Runs tasks immediately while preserving the future queue boundary."""

    def submit(self, task: TaskFn) -> None:
        task()


class ThreadPoolTaskExecutor:
    """Runs tasks in a local thread pool for the single-process MVP."""

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
    normalized = kind.strip().lower()
    if normalized in {"sync", "synchronous"}:
        return SynchronousTaskExecutor()
    if normalized in {"thread", "threadpool", "local_thread"}:
        return ThreadPoolTaskExecutor(max_workers=max_workers)
    raise ValueError(f"Unsupported task executor: {kind}")
