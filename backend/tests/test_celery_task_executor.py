from pathlib import Path

import psycopg
import pytest

from app.db.postgres import connect
from app.services.business_tasks import dispatch_business_task
from app.services.file_service import FileService
from app.services.task_executor import CeleryTaskExecutor, create_task_executor
from app.services.translation_service import TranslationService


class RecordingSendTask:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, kind: str, payload: dict) -> None:
        self.calls.append((kind, payload))


def test_create_task_executor_builds_celery_executor() -> None:
    assert isinstance(create_task_executor("celery"), CeleryTaskExecutor)


def test_celery_executor_rejects_closure_submit() -> None:
    with pytest.raises(RuntimeError):
        CeleryTaskExecutor(send_task=RecordingSendTask()).submit(lambda: None)


def test_translation_create_task_enqueues_celery_payload(tmp_path: Path, pg_dsn: str) -> None:
    conn = connect(pg_dsn)
    sender = RecordingSendTask()
    try:
        file_service = FileService(conn, workspace_dir=tmp_path / "workspace")
        source = file_service.save_generated_content("alice", "demo.docx", b"source")

        service = TranslationService(
            conn,
            file_service=file_service,
            translation_work_dir=tmp_path / "translation_work",
            translator=lambda *_args: "",
            task_executor=CeleryTaskExecutor(send_task=sender),
        )

        created = service.create_task("alice", source.id, "英语")

        assert created.status == "pending"
        assert sender.calls == [
            (
                "translation",
                {
                    "task_id": created.task_id,
                    "owner_username": "alice",
                    "file_id": source.id,
                    "target_language": "英语",
                    "api_key": None,
                },
            )
        ]
    finally:
        conn.close()


def test_dispatch_business_task_runs_translation(tmp_path: Path, pg_dsn: str, monkeypatch) -> None:
    """worker 端按 payload 重建 service 并执行任务的端到端（库内）验证。"""
    setup_conn = connect(pg_dsn)
    try:
        file_service = FileService(setup_conn, workspace_dir=tmp_path / "workspace")
        source = file_service.save_generated_content("alice", "demo.docx", b"source")
        service = TranslationService(
            setup_conn,
            file_service=file_service,
            translation_work_dir=tmp_path / "translation_work",
            translator=lambda *_args: "",
            task_executor=CeleryTaskExecutor(send_task=RecordingSendTask()),
        )
        created = service.create_task("alice", source.id, "英语")
    finally:
        setup_conn.close()

    def fake_translator(file_name: str, workspace_dir: str, target_language: str) -> str:
        source_path = Path(workspace_dir) / file_name
        output_path = Path(workspace_dir) / f"{source_path.stem}_{target_language}{source_path.suffix}"
        output_path.write_bytes(b"translated")
        return str(output_path)

    original_init = TranslationService.__init__

    def patched_init(self, conn, **kwargs):
        kwargs.setdefault("file_service", FileService(conn, workspace_dir=tmp_path / "workspace"))
        kwargs.setdefault("translation_work_dir", tmp_path / "translation_work")
        kwargs.setdefault("translator", fake_translator)
        original_init(self, conn, **kwargs)

    monkeypatch.setattr(TranslationService, "__init__", patched_init)
    monkeypatch.setattr("app.services.business_tasks.connect", lambda: connect(pg_dsn))

    dispatch_business_task(
        "translation",
        {
            "task_id": created.task_id,
            "owner_username": "alice",
            "file_id": source.id,
            "target_language": "英语",
        },
    )

    verify_conn = connect(pg_dsn)
    try:
        row = verify_conn.execute(
            "SELECT status, result_file_id FROM translation_tasks WHERE task_id = %s",
            (created.task_id,),
        ).fetchone()
        assert row["status"] == "succeeded"
        assert row["result_file_id"]
    finally:
        verify_conn.close()


def test_dispatch_business_task_rejects_unknown_kind(pg_dsn: str, monkeypatch) -> None:
    monkeypatch.setattr("app.services.business_tasks.connect", lambda: connect(pg_dsn))
    with pytest.raises(ValueError):
        dispatch_business_task("unknown", {})
