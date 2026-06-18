import json
from collections.abc import Callable

from app.db.postgres import connect
from app.repositories.code_audit_repository import CodeAuditRepository
from app.schemas.code_operations import CodeAuditRead
from app.services.code_execution_service import CodeOperationRecord

# 审计详情里不落库的字段：文件内容可能高达 1MB，审计只需要操作元数据。
_DETAIL_EXCLUDED_KEYS = {"content"}

AuditSink = Callable[[CodeOperationRecord, dict | None], None]


def create_default_audit_sink() -> AuditSink:
    """返回把 code agent 审计记录写入默认 SQLite 的 sink。

    LangGraph 工具可能在不同线程里执行，所以每条记录都用独立的短连接写入，
    避免跨线程复用请求级连接。审计失败不会影响工具执行（调用方已兜底）。
    """

    def sink(record: CodeOperationRecord, detail: dict | None) -> None:
        conn = connect()
        try:
            repository = CodeAuditRepository(conn)
            repository.initialize()
            repository.create(
                record_id=record.operation_id,
                owner_username=record.owner_username,
                conversation_id=record.conversation_id,
                agent_name=record.agent_name,
                tool_name=record.tool_name,
                status=record.status,
                target=record.target,
                message=record.message,
                detail=_clean_detail(detail),
                started_at=record.started_at.isoformat(),
                finished_at=record.finished_at.isoformat(),
            )
        finally:
            conn.close()

    return sink


def _clean_detail(detail: dict | None) -> dict | None:
    if not detail:
        return None
    return {key: value for key, value in detail.items() if key not in _DETAIL_EXCLUDED_KEYS}


def audit_row_to_read(row) -> CodeAuditRead:
    detail_json = row["detail_json"]
    return CodeAuditRead(
        record_id=row["id"],
        conversation_id=row["conversation_id"],
        agent_name=row["agent_name"],
        tool_name=row["tool_name"],
        status=row["status"],
        target=row["target"],
        message=row["message"],
        detail=json.loads(detail_json) if detail_json else None,
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )
