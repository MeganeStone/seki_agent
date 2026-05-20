from pathlib import Path
import time

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.sqlite import connect
from app.main import create_app
from app.services.file_service import FileService
from app.services.task_executor import SynchronousTaskExecutor, TaskFn, ThreadPoolTaskExecutor, create_task_executor
from app.services.translation_service import TranslationService


class DeferredTaskExecutor:
    def __init__(self) -> None:
        self.tasks: list[TaskFn] = []

    def submit(self, task: TaskFn) -> None:
        self.tasks.append(task)

    def run_all(self) -> None:
        for task in list(self.tasks):
            task()
        self.tasks.clear()


def test_synchronous_task_executor_runs_task_immediately() -> None:
    calls: list[str] = []

    SynchronousTaskExecutor().submit(lambda: calls.append("ran"))

    assert calls == ["ran"]


def test_create_task_executor_builds_thread_pool() -> None:
    executor = create_task_executor("thread", max_workers=1)
    try:
        assert isinstance(executor, ThreadPoolTaskExecutor)
    finally:
        executor.shutdown()


def test_app_lifespan_uses_configured_thread_pool_executor(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "task_executor", "thread")
    monkeypatch.setattr(settings, "task_executor_max_workers", 1)

    with TestClient(create_app()) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert isinstance(client.app.state.task_executor, ThreadPoolTaskExecutor)


def test_translation_service_can_defer_task_execution(tmp_path: Path) -> None:
    conn = connect(tmp_path / "test.db")
    try:
        file_service = FileService(conn, workspace_dir=tmp_path / "workspace")
        source = file_service.save_generated_content("alice", "demo.docx", b"source")
        executor = DeferredTaskExecutor()

        def fake_translator(file_name: str, workspace_dir: str, target_language: str) -> str:
            source_path = Path(workspace_dir) / file_name
            output_path = Path(workspace_dir) / f"{source_path.stem}_{target_language}{source_path.suffix}"
            output_path.write_bytes(b"translated")
            return str(output_path)

        service = TranslationService(
            conn,
            file_service=file_service,
            translation_work_dir=tmp_path / "translation_work",
            translator=fake_translator,
            task_executor=executor,
        )

        created = service.create_task("alice", source.id, "英语")

        assert created.status == "pending"
        assert created.result_file_id is None
        assert len(executor.tasks) == 1

        executor.run_all()
        completed = service.get_task("alice", created.task_id)

        assert completed.status == "succeeded"
        assert completed.result_file_id is not None
    finally:
        conn.close()


def test_translation_service_runs_with_thread_pool_executor(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = connect(db_path)
    executor = ThreadPoolTaskExecutor(max_workers=1)
    try:
        file_service = FileService(conn, workspace_dir=tmp_path / "workspace")
        source = file_service.save_generated_content("alice", "demo.docx", b"source")

        def fake_translator(file_name: str, workspace_dir: str, target_language: str) -> str:
            source_path = Path(workspace_dir) / file_name
            output_path = Path(workspace_dir) / f"{source_path.stem}_{target_language}{source_path.suffix}"
            output_path.write_bytes(b"translated")
            return str(output_path)

        service = TranslationService(
            conn,
            file_service=file_service,
            translation_work_dir=tmp_path / "translation_work",
            translator=fake_translator,
            task_executor=executor,
            db_path=db_path,
        )

        created = service.create_task("alice", source.id, "英语")
        assert created.status in {"pending", "succeeded"}

        deadline = time.monotonic() + 5
        completed = service.get_task("alice", created.task_id)
        while completed.status == "pending" and time.monotonic() < deadline:
            time.sleep(0.05)
            completed = service.get_task("alice", created.task_id)

        assert completed.status == "succeeded"
        assert completed.result_file_id is not None
    finally:
        executor.shutdown()
        conn.close()
