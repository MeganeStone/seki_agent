import psycopg
from typing import Literal

from fastapi import HTTPException, status

from app.repositories.diff_repository import DiffRepository
from app.repositories.spi_repository import SpiRepository
from app.repositories.translation_repository import TranslationRepository
from app.schemas.tasks import TaskListResponse, TaskRead, TaskType


class TaskService:
    def __init__(self, conn: psycopg.Connection):
        self.translation_tasks = TranslationRepository(conn)
        self.spi_tasks = SpiRepository(conn)
        self.diff_tasks = DiffRepository(conn)
        self.translation_tasks.initialize()
        self.spi_tasks.initialize()
        self.diff_tasks.initialize()

    def list_tasks(self, owner_username: str, limit: int = 50) -> TaskListResponse:
        clean_limit = min(max(limit, 1), 200)
        tasks = [
            *(self._to_task(row, "translation") for row in self.translation_tasks.list_for_owner(owner_username, clean_limit)),
            *(self._to_task(row, "spi") for row in self.spi_tasks.list_for_owner(owner_username, clean_limit)),
            *(self._to_task(row, "diff") for row in self.diff_tasks.list_for_owner(owner_username, clean_limit)),
        ]
        tasks.sort(key=lambda task: task.updated_at, reverse=True)
        return TaskListResponse(items=tasks[:clean_limit])

    def get_task(self, owner_username: str, task_id: str) -> TaskRead:
        lookups: list[tuple[TaskType, object]] = [
            ("translation", self.translation_tasks),
            ("spi", self.spi_tasks),
            ("diff", self.diff_tasks),
        ]
        for task_type, repository in lookups:
            row = repository.get_for_owner(task_id, owner_username)
            if row is not None:
                return self._to_task(row, task_type)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    def cancel_task(self, owner_username: str, task_id: str) -> TaskRead:
        lookups: list[tuple[TaskType, object]] = [
            ("translation", self.translation_tasks),
            ("spi", self.spi_tasks),
            ("diff", self.diff_tasks),
        ]
        for task_type, repository in lookups:
            row = repository.get_for_owner(task_id, owner_username)
            if row is None:
                continue
            cancelled = repository.cancel_for_owner(task_id, owner_username)
            return self._to_task(cancelled or row, task_type)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    @staticmethod
    def _to_task(row: dict, task_type: Literal["translation", "spi", "diff"]) -> TaskRead:
        return TaskRead(
            task_id=row["task_id"],
            type=task_type,
            status=row["status"],
            result_file_id=row["result_file_id"],
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
