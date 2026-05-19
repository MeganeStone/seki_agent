import importlib.util
import shutil
import sqlite3
import sys
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, status

from app.core.config import get_settings
from app.repositories.translation_repository import TranslationRepository
from app.schemas.translation import TranslationTaskRead
from app.services.file_service import FileService


Translator = Callable[[str, str, str], str]


class TranslationService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        file_service: FileService | None = None,
        translation_work_dir: Path | None = None,
        legacy_src_dir: Path | None = None,
        translator: Translator | None = None,
    ):
        settings = get_settings()
        self.conn = conn
        self.tasks = TranslationRepository(conn)
        self.tasks.initialize()
        self.file_service = file_service or FileService(conn)
        self.translation_work_dir = translation_work_dir or settings.translation_work_dir
        self.legacy_src_dir = legacy_src_dir or settings.legacy_src_dir
        self.translator = translator or self._load_legacy_translator()

    def create_task(self, owner_username: str, file_id: str, target_language: str) -> TranslationTaskRead:
        clean_target_language = target_language.strip()
        if not clean_target_language:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="target_language is required")

        task_id = uuid4().hex
        self.tasks.create(task_id, owner_username, file_id, clean_target_language)

        try:
            source_path, source_name = self.file_service.get_file_path(owner_username, file_id)
            self._validate_document(source_name)

            task_workspace = self.translation_work_dir / task_id
            task_workspace.mkdir(parents=True, exist_ok=True)
            local_source = task_workspace / source_name
            shutil.copy2(source_path, local_source)

            self.translator(source_name, str(task_workspace), clean_target_language)
            output_path = task_workspace / f"{local_source.stem}_{clean_target_language}{local_source.suffix}"
            if not output_path.exists() or not output_path.is_file():
                raise RuntimeError("Translator did not produce an output file")

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
            return self._to_schema(row)
        except HTTPException as exc:
            row = self.tasks.update_result(task_id, owner_username, status="failed", error=str(exc.detail))
            return self._to_schema(row)
        except Exception as exc:
            row = self.tasks.update_result(task_id, owner_username, status="failed", error=str(exc))
            return self._to_schema(row)
        finally:
            shutil.rmtree(self.translation_work_dir / task_id, ignore_errors=True)

    def get_task(self, owner_username: str, task_id: str) -> TranslationTaskRead:
        row = self.tasks.get_for_owner(task_id, owner_username)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Translation task not found")
        return self._to_schema(row)

    def _load_legacy_translator(self) -> Translator:
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

    @staticmethod
    def _to_schema(row: sqlite3.Row) -> TranslationTaskRead:
        return TranslationTaskRead(
            task_id=row["task_id"],
            status=row["status"],
            target_language=row["target_language"],
            result_file_id=row["result_file_id"],
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

