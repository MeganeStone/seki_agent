import difflib
import shutil
import sqlite3
import stat
import subprocess
import tarfile
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, status

from app.core.config import get_settings
from app.db.sqlite import connect
from app.repositories.diff_repository import DiffRepository
from app.schemas.diff import DiffSummary, DiffTaskRead
from app.services.file_service import FileService
from app.services.task_executor import SynchronousTaskExecutor, TaskExecutor, ThreadPoolTaskExecutor


Comparator = Callable[[Path, Path, str, str, str], str]


class DiffService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        file_service: FileService | None = None,
        diff_work_dir: Path | None = None,
        legacy_src_dir: Path | None = None,
        comparator: Comparator | None = None,
        task_executor: TaskExecutor | None = None,
        db_path: Path | None = None,
    ):
        settings = get_settings()
        self.conn = conn
        self.tasks = DiffRepository(conn)
        self.tasks.initialize()
        self.file_service = file_service or FileService(conn)
        self.diff_work_dir = diff_work_dir or settings.diff_work_dir
        self.legacy_src_dir = legacy_src_dir or settings.legacy_src_dir
        self.db_path = db_path or settings.database_path
        self.comparator = comparator or self._compare_archives
        self.task_executor = task_executor or SynchronousTaskExecutor()

    def create_task(self, owner_username: str, left_file_id: str, right_file_id: str) -> DiffTaskRead:
        task_id = uuid4().hex
        self.tasks.create(task_id, owner_username, left_file_id, right_file_id)
        self.task_executor.submit(lambda: self._run_task_in_executor(task_id, owner_username, left_file_id, right_file_id))
        return self.get_task(owner_username, task_id)

    def _run_task_in_executor(self, task_id: str, owner_username: str, left_file_id: str, right_file_id: str) -> None:
        if isinstance(self.task_executor, ThreadPoolTaskExecutor):
            conn = connect(self.db_path)
            try:
                service = DiffService(
                    conn,
                    file_service=FileService(conn, workspace_dir=self.file_service.workspace_dir),
                    diff_work_dir=self.diff_work_dir,
                    legacy_src_dir=self.legacy_src_dir,
                    comparator=self.comparator,
                    task_executor=SynchronousTaskExecutor(),
                    db_path=self.db_path,
                )
                service._run_task(task_id, owner_username, left_file_id, right_file_id)
            finally:
                conn.close()
            return

        self._run_task(task_id, owner_username, left_file_id, right_file_id)

    def _run_task(self, task_id: str, owner_username: str, left_file_id: str, right_file_id: str) -> None:
        try:
            if self._is_cancelled(task_id, owner_username):
                return
            self.tasks.update_result(task_id, owner_username, status="running")
            left_path, left_name = self.file_service.get_file_path(owner_username, left_file_id)
            right_path, right_name = self.file_service.get_file_path(owner_username, right_file_id)
            self._validate_archive(left_name)
            self._validate_archive(right_name)

            result_text = self.comparator(left_path, right_path, left_name, right_name, task_id)
            if self._is_cancelled(task_id, owner_username):
                return
            result_file = self.file_service.save_generated_content(
                owner_username,
                f"diff_{task_id}.txt",
                result_text.encode("utf-8"),
            )
            row = self.tasks.update_result(
                task_id,
                owner_username,
                status="succeeded",
                result_text=result_text,
                result_file_id=result_file.id,
            )
            self._to_schema(row)
        except HTTPException as exc:
            if self._is_cancelled(task_id, owner_username):
                return
            self.tasks.update_result(
                task_id,
                owner_username,
                status="failed",
                error=str(exc.detail),
            )
        except Exception as exc:
            if self._is_cancelled(task_id, owner_username):
                return
            self.tasks.update_result(
                task_id,
                owner_username,
                status="failed",
                error=str(exc),
            )

    def get_task(self, owner_username: str, task_id: str) -> DiffTaskRead:
        row = self.tasks.get_for_owner(task_id, owner_username)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diff task not found")
        return self._to_schema(row)

    def _compare_archives(self, left_path: Path, right_path: Path, left_name: str, right_name: str, task_id: str) -> str:
        work_root = self.diff_work_dir / task_id
        left_dir = work_root / "A"
        right_dir = work_root / "B"
        left_dir.mkdir(parents=True, exist_ok=True)
        right_dir.mkdir(parents=True, exist_ok=True)

        try:
            self._extract_tar_gz(left_path, left_dir)
            self._extract_tar_gz(right_path, right_dir)
            self._run_legacy_scripts(left_dir)
            self._run_legacy_scripts(right_dir)

            left_bin = self._load_lines(left_dir / "bin_size.txt")
            right_bin = self._load_lines(right_dir / "bin_size.txt")
            left_lib = self._load_lines(left_dir / "lib_size.txt")
            right_lib = self._load_lines(right_dir / "lib_size.txt")

            diff_bin = "\n".join(difflib.unified_diff(left_bin, right_bin, fromfile=left_name, tofile=right_name, lineterm=""))
            diff_lib = "\n".join(difflib.unified_diff(left_lib, right_lib, fromfile=left_name, tofile=right_name, lineterm=""))

            parts = []
            parts.append("=== bin_size.txt diff ===\n" + diff_bin if diff_bin else "bin_size.txt no diff")
            parts.append("=== lib_size.txt diff ===\n" + diff_lib if diff_lib else "lib_size.txt no diff")
            return "\n\n".join(parts)
        finally:
            shutil.rmtree(work_root, ignore_errors=True)

    def _run_legacy_scripts(self, target_dir: Path) -> None:
        bin_script = self.legacy_src_dir / "bin_srcdiff.sh"
        lib_script = self.legacy_src_dir / "lib_srcdiff.sh"
        if not bin_script.exists() or not lib_script.exists():
            raise RuntimeError("Missing bin_srcdiff.sh or lib_srcdiff.sh")

        for script in (bin_script, lib_script):
            copied = target_dir / script.name
            shutil.copy2(script, copied)
            copied.chmod(copied.stat().st_mode | stat.S_IEXEC)

        shell = shutil.which("bash") or shutil.which("sh")
        if not shell:
            raise RuntimeError("bash or sh is required to run legacy diff scripts")

        for script_name in ("bin_srcdiff.sh", "lib_srcdiff.sh"):
            proc = subprocess.run(
                [shell, f"./{script_name}"],
                cwd=target_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=300,
            )
            if proc.returncode != 0:
                raise RuntimeError(
                    f"Legacy diff script failed: {script_name}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
                )

    @staticmethod
    def _extract_tar_gz(archive: Path, destination: Path) -> None:
        if not tarfile.is_tarfile(archive):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only .tar.gz archives are supported")
        with tarfile.open(archive, "r:gz") as tar:
            destination_root = destination.resolve()
            for member in tar.getmembers():
                member_path = (destination / member.name).resolve()
                if destination_root != member_path and destination_root not in member_path.parents:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archive contains unsafe path")
            tar.extractall(destination)

    @staticmethod
    def _validate_archive(filename: str) -> None:
        if not filename.endswith(".tar.gz"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only .tar.gz archives are supported")

    @staticmethod
    def _load_lines(path: Path) -> list[str]:
        if not path.exists():
            return []
        return path.read_text(encoding="utf-8", errors="ignore").splitlines()

    @staticmethod
    def _to_schema(row: sqlite3.Row) -> DiffTaskRead:
        result_text = row["result_text"]
        bin_changed = bool(result_text and "=== bin_size.txt diff ===" in result_text)
        lib_changed = bool(result_text and "=== lib_size.txt diff ===" in result_text)
        summary = None
        if row["status"] == "succeeded":
            summary = DiffSummary(
                changed=bin_changed or lib_changed,
                bin_changed=bin_changed,
                lib_changed=lib_changed,
            )
        return DiffTaskRead(
            task_id=row["task_id"],
            status=row["status"],
            summary=summary,
            result_file_id=row["result_file_id"],
            result_text=result_text,
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _is_cancelled(self, task_id: str, owner_username: str) -> bool:
        row = self.tasks.get_for_owner(task_id, owner_username)
        return row is not None and row["status"] == "cancelled"
