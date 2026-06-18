import importlib.util
import json
import shutil
import psycopg
import sys
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, status

from app.core.config import get_settings
from app.db.postgres import connect
from app.repositories.spi_repository import SpiRepository
from app.schemas.spi import SpiTaskRead
from app.services.file_service import FileService
from app.services.task_executor import (
    CeleryTaskExecutor,
    SynchronousTaskExecutor,
    TaskExecutor,
    ThreadPoolTaskExecutor,
)


SpiParser = Callable[[Path, str, str, str], dict]


class SpiService:
    def __init__(
        self,
        conn: psycopg.Connection,
        file_service: FileService | None = None,
        spi_work_dir: Path | None = None,
        legacy_src_dir: Path | None = None,
        parser: SpiParser | None = None,
        task_executor: TaskExecutor | None = None,
        database_url: str | None = None,
    ):
        settings = get_settings()
        self.conn = conn
        self.tasks = SpiRepository(conn)
        self.tasks.initialize()
        self.file_service = file_service or FileService(conn)
        self.spi_work_dir = spi_work_dir or settings.spi_work_dir
        self.legacy_src_dir = legacy_src_dir or settings.legacy_src_dir
        self.database_url = database_url or settings.database_url
        self.parser = parser or self._load_legacy_parser()
        self.task_executor = task_executor or SynchronousTaskExecutor()

    def create_task(self, owner_username: str, file_ids: str | list[str]) -> SpiTaskRead:
        clean_file_ids = [file_ids] if isinstance(file_ids, str) else list(file_ids)
        if not clean_file_ids:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="file_ids is required")
        task_id = uuid4().hex
        self.tasks.create(task_id, owner_username, json.dumps(clean_file_ids, ensure_ascii=False))
        if isinstance(self.task_executor, CeleryTaskExecutor):
            self.task_executor.enqueue(
                "spi",
                {
                    "task_id": task_id,
                    "owner_username": owner_username,
                    "file_ids": clean_file_ids,
                },
            )
        else:
            self.task_executor.submit(lambda: self._run_task_in_executor(task_id, owner_username, clean_file_ids))
        return self.get_task(owner_username, task_id)

    def _run_task_in_executor(self, task_id: str, owner_username: str, file_ids: list[str]) -> None:
        if isinstance(self.task_executor, ThreadPoolTaskExecutor):
            conn = connect(self.database_url)
            try:
                service = SpiService(
                    conn,
                    file_service=FileService(conn, workspace_dir=self.file_service.workspace_dir),
                    spi_work_dir=self.spi_work_dir,
                    legacy_src_dir=self.legacy_src_dir,
                    parser=self.parser,
                    task_executor=SynchronousTaskExecutor(),
                    database_url=self.database_url,
                )
                service._run_task(task_id, owner_username, file_ids)
            finally:
                conn.close()
            return

        self._run_task(task_id, owner_username, file_ids)

    def _run_task(self, task_id: str, owner_username: str, file_ids: list[str]) -> None:
        try:
            if self._is_cancelled(task_id, owner_username):
                return
            self.tasks.update_result(task_id, owner_username, status="running")
            task_workspace = self.spi_work_dir / task_id
            logs_dir = task_workspace / "parse_spi" / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            for file_id in file_ids:
                log_path, log_name = self.file_service.get_file_path(owner_username, file_id)
                self._validate_log_file(log_name)
                shutil.copy2(log_path, logs_dir / log_name)

            result = self.parser(task_workspace, "parse_spi/logs", "spi_id.txt", "template.xlsx")
            if not result.get("success"):
                row = self.tasks.update_result(
                    task_id,
                    owner_username,
                    status="failed",
                    error=str(result.get("message") or "SPI parse failed"),
                )
                self._to_schema(row)
                return

            output_path = Path(result["output_path"])
            if not output_path.exists() or not output_path.is_file():
                raise RuntimeError("SPI parser did not produce an Excel file")

            if self._is_cancelled(task_id, owner_username):
                return
            result_file = self.file_service.save_generated_content(
                owner_username,
                output_path.name,
                output_path.read_bytes(),
            )
            row = self.tasks.update_result(
                task_id,
                owner_username,
                status="succeeded",
                result_file_id=result_file.id,
            )
            self._to_schema(row)
        except HTTPException as exc:
            if self._is_cancelled(task_id, owner_username):
                return
            self.tasks.update_result(task_id, owner_username, status="failed", error=str(exc.detail))
        except Exception as exc:
            if self._is_cancelled(task_id, owner_username):
                return
            self.tasks.update_result(task_id, owner_username, status="failed", error=str(exc))
        finally:
            shutil.rmtree(self.spi_work_dir / task_id, ignore_errors=True)

    def get_task(self, owner_username: str, task_id: str) -> SpiTaskRead:
        row = self.tasks.get_for_owner(task_id, owner_username)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SPI task not found")
        return self._to_schema(row)

    def _load_legacy_parser(self) -> SpiParser:
        module_path = self.legacy_src_dir / "parse_SPI.py"
        if not module_path.exists():
            raise RuntimeError("Legacy parse_SPI.py not found")

        if str(self.legacy_src_dir) not in sys.path:
            sys.path.insert(0, str(self.legacy_src_dir))

        legacy_parse_spi_root = self.legacy_src_dir / "parse_spi"
        if legacy_parse_spi_root.exists():
            import os

            os.environ.setdefault("PARSE_SPI_ROOT", str(legacy_parse_spi_root))

        spec = importlib.util.spec_from_file_location("legacy_parse_SPI", module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Failed to load legacy parse_SPI.py")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.run_parse_spi

    @staticmethod
    def _validate_log_file(filename: str) -> None:
        if not filename.lower().endswith(".log"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only .log files are supported")

    def _to_schema(self, row: dict) -> SpiTaskRead:
        result_filename = self._result_filename(row["owner_username"], row["result_file_id"])
        return SpiTaskRead(
            task_id=row["task_id"],
            status=row["status"],
            result_file_id=row["result_file_id"],
            result_filename=result_filename,
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _result_filename(self, owner_username: str, file_id: str | None) -> str | None:
        if not file_id:
            return None
        try:
            return self.file_service.get_file(owner_username, file_id).filename
        except HTTPException:
            return None

    def _is_cancelled(self, task_id: str, owner_username: str) -> bool:
        row = self.tasks.get_for_owner(task_id, owner_username)
        return row is not None and row["status"] == "cancelled"
