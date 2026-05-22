import importlib.util
import os
import shutil
import sqlite3
import sys
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, status

from app.core.api_keys import temporary_env_api_key
from app.core.config import get_settings
from app.db.sqlite import connect
from app.repositories.translation_repository import TranslationRepository
from app.schemas.translation import TranslationTaskRead
from app.services.file_service import FileService
from app.services.task_executor import SynchronousTaskExecutor, TaskExecutor, ThreadPoolTaskExecutor


Translator = Callable[[str, str, str], str]


class TranslationService:
    """文档翻译任务服务。

    新框架负责鉴权、任务表、文件表和执行器；真正的 Office 翻译能力暂时复用
    `backend/legacy/tbox_custom_translator.py`，因此这里也是 legacy 迁移边界。
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        file_service: FileService | None = None,
        translation_work_dir: Path | None = None,
        legacy_src_dir: Path | None = None,
        translator: Translator | None = None,
        task_executor: TaskExecutor | None = None,
        db_path: Path | None = None,
    ):
        settings = get_settings()
        self.conn = conn
        self.tasks = TranslationRepository(conn)
        self.tasks.initialize()
        self.file_service = file_service or FileService(conn)
        self.translation_work_dir = translation_work_dir or settings.translation_work_dir
        self.legacy_src_dir = legacy_src_dir or settings.legacy_src_dir
        self.db_path = db_path or settings.database_path
        self.translator = translator or self._load_legacy_translator()
        self.uses_legacy_translator = translator is None
        self.task_executor = task_executor or SynchronousTaskExecutor()

    def create_task(
        self,
        owner_username: str,
        file_id: str,
        target_language: str,
        api_key: str | None = None,
    ) -> TranslationTaskRead:
        """创建翻译任务并提交后台执行。"""
        clean_target_language = target_language.strip()
        if not clean_target_language:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="target_language is required")

        task_id = uuid4().hex
        self.tasks.create(task_id, owner_username, file_id, clean_target_language)
        self.task_executor.submit(
            lambda: self._run_task_in_executor(task_id, owner_username, file_id, clean_target_language, api_key)
        )
        return self.get_task(owner_username, task_id)

    def _run_task_in_executor(
        self,
        task_id: str,
        owner_username: str,
        file_id: str,
        target_language: str,
        api_key: str | None = None,
    ) -> None:
        """在线程池执行时重新创建 SQLite 连接。

        sqlite3.Connection 默认不能跨线程安全复用，所以后台线程里要重新 connect。
        同步执行器则直接使用当前 service。
        """
        if isinstance(self.task_executor, ThreadPoolTaskExecutor):
            conn = connect(self.db_path)
            try:
                service = TranslationService(
                    conn,
                    file_service=FileService(conn, workspace_dir=self.file_service.workspace_dir),
                    translation_work_dir=self.translation_work_dir,
                    legacy_src_dir=self.legacy_src_dir,
                    translator=self.translator,
                    task_executor=SynchronousTaskExecutor(),
                    db_path=self.db_path,
                )
                service._run_task(task_id, owner_username, file_id, target_language, api_key=api_key)
            finally:
                conn.close()
            return

        self._run_task(task_id, owner_username, file_id, target_language, api_key=api_key)

    def _run_task(
        self,
        task_id: str,
        owner_username: str,
        file_id: str,
        target_language: str,
        api_key: str | None = None,
    ) -> None:
        """执行单个翻译任务，并把成功/失败状态写回任务表。"""
        try:
            if self._is_cancelled(task_id, owner_username):
                return
            self.tasks.update_result(task_id, owner_username, status="running")
            if self.uses_legacy_translator and not (os.environ.get("TRANSLATE_API_KEY") or api_key):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="请先配置翻译 API key，或在前端输入临时 API key。",
                )
            source_path, source_name = self.file_service.get_file_path(owner_username, file_id)
            self._validate_document(source_name)

            task_workspace = self.translation_work_dir / task_id
            task_workspace.mkdir(parents=True, exist_ok=True)
            local_source = task_workspace / source_name
            shutil.copy2(source_path, local_source)

            with temporary_env_api_key("TRANSLATE_API_KEY", api_key):
                self.translator(source_name, str(task_workspace), target_language)
            output_path = task_workspace / f"{local_source.stem}_{target_language}{local_source.suffix}"
            if not output_path.exists() or not output_path.is_file():
                raise RuntimeError("Translator did not produce an output file")

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
            shutil.rmtree(self.translation_work_dir / task_id, ignore_errors=True)

    def get_task(self, owner_username: str, task_id: str) -> TranslationTaskRead:
        row = self.tasks.get_for_owner(task_id, owner_username)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Translation task not found")
        return self._to_schema(row)

    def _load_legacy_translator(self) -> Translator:
        """动态加载 legacy 翻译函数，避免把旧目录做成完整 Python 包。"""
        module_path = self.legacy_src_dir / "tbox_custom_translator.py"
        if not module_path.exists():
            raise RuntimeError("Legacy tbox_custom_translator.py not found")

        if str(self.legacy_src_dir) not in sys.path:
            sys.path.insert(0, str(self.legacy_src_dir))

        spec = importlib.util.spec_from_file_location("legacy_tbox_custom_translator", module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Failed to load legacy translator")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.translate_file

    @staticmethod
    def _validate_document(filename: str) -> None:
        suffix = Path(filename).suffix.lower()
        if suffix not in {".pptx", ".xlsx", ".docx"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only .pptx, .xlsx and .docx files are supported",
            )

    def _to_schema(self, row: sqlite3.Row) -> TranslationTaskRead:
        return TranslationTaskRead(
            task_id=row["task_id"],
            status=row["status"],
            target_language=row["target_language"],
            result_file_id=row["result_file_id"],
            result_filename=self._result_filename(row["owner_username"], row["result_file_id"]),
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
