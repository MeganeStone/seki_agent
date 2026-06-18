"""自建 Agent 运行追踪服务。

每轮对话开始时创建一条 run；流式过程中的工具调用、模型 token 用量逐条写入
event；结束时把最终状态、答案预览和累计 token 写回 run。追踪失败只记日志，
不影响对话主流程。
"""
import logging
from datetime import datetime, timezone
from time import monotonic
from uuid import uuid4

import psycopg
from fastapi import HTTPException, status

from app.repositories.agent_trace_repository import AgentTraceRepository
from app.schemas.agent_trace import (
    AgentTraceEventRead,
    AgentTraceRunDetailResponse,
    AgentTraceRunRead,
)

logger = logging.getLogger("seki.trace")

_PREVIEW_LIMIT = 500


class TraceRun:
    """一次进行中的 run 的内存状态，由 AgentTraceService.start_run 创建。"""

    def __init__(self, run_id: str, owner_username: str):
        self.run_id = run_id
        self.owner_username = owner_username
        self.started_monotonic = monotonic()
        self.seq = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def next_seq(self) -> int:
        self.seq += 1
        return self.seq


class AgentTraceService:
    def __init__(self, conn: psycopg.Connection):
        self.conn = conn
        self.runs = AgentTraceRepository(conn)
        self.runs.initialize()

    # ---- 采集 ----

    def start_run(
        self,
        owner_username: str,
        conversation_id: str,
        agent_name: str,
        message: str,
    ) -> TraceRun | None:
        try:
            run_id = uuid4().hex
            self.runs.create_run(
                run_id,
                owner_username,
                conversation_id,
                agent_name,
                _preview(message),
                _now(),
            )
            return TraceRun(run_id, owner_username)
        except Exception:
            logger.exception("trace start_run failed")
            return None

    def record_tool_event(
        self,
        run: TraceRun | None,
        name: str,
        status_text: str,
        preview: str = "",
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        if run is None:
            return
        try:
            self.runs.add_event(
                uuid4().hex,
                run.run_id,
                run.owner_username,
                run.next_seq(),
                "tool_call",
                name,
                status_text,
                _preview(preview),
                error,
                None,
                None,
                duration_ms,
                _now(),
            )
        except Exception:
            logger.exception("trace record_tool_event failed")

    def record_model_usage(
        self,
        run: TraceRun | None,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        if run is None:
            return
        run.input_tokens += input_tokens
        run.output_tokens += output_tokens
        try:
            self.runs.add_event(
                uuid4().hex,
                run.run_id,
                run.owner_username,
                run.next_seq(),
                "model_call",
                model_name,
                "succeeded",
                "",
                None,
                input_tokens,
                output_tokens,
                None,
                _now(),
            )
        except Exception:
            logger.exception("trace record_model_usage failed")

    def finish_run(
        self,
        run: TraceRun | None,
        status_text: str,
        answer: str = "",
        error: str | None = None,
        agent_name: str | None = None,
    ) -> None:
        if run is None:
            return
        try:
            self.runs.finish_run(
                run.run_id,
                run.owner_username,
                status_text,
                _preview(answer),
                error,
                run.input_tokens,
                run.output_tokens,
                _now(),
                int((monotonic() - run.started_monotonic) * 1000),
                agent_name=agent_name,
            )
        except Exception:
            logger.exception("trace finish_run failed")

    # ---- 查询 ----

    def list_runs(
        self,
        owner_username: str,
        conversation_id: str | None = None,
        limit: int = 50,
    ) -> list[AgentTraceRunRead]:
        return [self._to_run(row) for row in self.runs.list_runs(owner_username, conversation_id, limit)]

    def get_run_detail(self, owner_username: str, run_id: str) -> AgentTraceRunDetailResponse:
        row = self.runs.get_run(run_id, owner_username)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trace run not found")
        events = [self._to_event(item) for item in self.runs.list_events(run_id, owner_username)]
        return AgentTraceRunDetailResponse(run=self._to_run(row), events=events)

    @staticmethod
    def _to_run(row: dict) -> AgentTraceRunRead:
        return AgentTraceRunRead(
            run_id=row["id"],
            conversation_id=row["conversation_id"],
            agent_name=row["agent_name"],
            status=row["status"],
            input_preview=row["input_preview"] or "",
            answer_preview=row["answer_preview"] or "",
            error=row["error"],
            input_tokens=int(row["input_tokens"] or 0),
            output_tokens=int(row["output_tokens"] or 0),
            total_tokens=int(row["total_tokens"] or 0),
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            duration_ms=row["duration_ms"],
        )

    @staticmethod
    def _to_event(row: dict) -> AgentTraceEventRead:
        return AgentTraceEventRead(
            event_id=row["id"],
            seq=int(row["seq"]),
            event_type=row["event_type"],
            name=row["name"],
            status=row["status"],
            preview=row["preview"] or "",
            error=row["error"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            duration_ms=row["duration_ms"],
            created_at=row["created_at"],
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _preview(text: str, limit: int = _PREVIEW_LIMIT) -> str:
    clean = (text or "").strip()
    if len(clean) <= limit:
        return clean
    return f"{clean[:limit]}..."
