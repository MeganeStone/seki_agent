import json
import sqlite3
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException, status

from app.repositories.chat_repository import ChatRepository
from app.repositories.code_operation_repository import CodeOperationRepository
from app.schemas.code_operations import CodeOperationRead, CodeOperationResult
from app.services.code_agent_tools import CodeAgentFileTool
from app.services.code_execution_service import CodeExecutionResult


class CodeOperationService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        file_tool: CodeAgentFileTool | None = None,
        pending_ttl_minutes: int = 60,
    ):
        self.conn = conn
        self.operations = CodeOperationRepository(conn)
        self.operations.initialize()
        self.chats = ChatRepository(conn)
        self.chats.initialize()
        self.file_tool = file_tool
        self.pending_ttl_minutes = pending_ttl_minutes

    def create_pending_from_result(
        self,
        owner_username: str,
        conversation_id: str,
        agent_name: str,
        operation_type: str,
        payload: dict,
    ) -> CodeOperationRead:
        conversation = self.chats.get_conversation(conversation_id, owner_username)
        if conversation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

        expires_at = datetime.now(timezone.utc) + timedelta(minutes=self.pending_ttl_minutes)
        row = self.operations.create(
            uuid4().hex,
            owner_username,
            conversation_id,
            agent_name,
            operation_type,
            payload,
            expires_at,
        )
        return self._to_read(row)

    def list_operations(
        self,
        owner_username: str,
        conversation_id: str | None = None,
        operation_status: str | None = None,
        limit: int = 50,
    ) -> list[CodeOperationRead]:
        rows = self.operations.list_for_owner(owner_username, conversation_id, operation_status, limit)
        return [self._to_read(row) for row in rows]

    def get_operation(self, owner_username: str, operation_id: str) -> CodeOperationRead:
        row = self.operations.get_for_owner(operation_id, owner_username)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending operation not found")
        return self._to_read(row)

    def cancel_operation(self, owner_username: str, operation_id: str) -> CodeOperationRead:
        row = self.operations.get_for_owner(operation_id, owner_username)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending operation not found")
        if row["status"] != "pending":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Operation is not pending")
        updated = self.operations.update_status(
            operation_id,
            owner_username,
            "cancelled",
            {"message": "用户已取消该操作。"},
        )
        if updated is None:
            raise RuntimeError("Failed to cancel pending operation")
        return self._to_read(updated)

    def confirm_operation(self, owner_username: str, operation_id: str) -> CodeOperationRead:
        row = self.operations.get_for_owner(operation_id, owner_username)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending operation not found")
        if row["status"] != "pending":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Operation is not pending")
        if self._is_expired(row["expires_at"]):
            updated = self.operations.update_status(
                operation_id,
                owner_username,
                "expired",
                {"message": "该待确认操作已过期。"},
            )
            if updated is None:
                raise RuntimeError("Failed to expire pending operation")
            return self._to_read(updated)

        result = self._execute_confirmed(row)
        next_status = "executed" if result.status == "succeeded" else "failed"
        updated = self.operations.update_status(
            operation_id,
            owner_username,
            next_status,
            {
                "status": result.status,
                "message": result.message,
                "data": result.data,
            },
        )
        if updated is None:
            raise RuntimeError("Failed to update pending operation")

        self.chats.add_message(
            uuid4().hex,
            row["conversation_id"],
            owner_username,
            "assistant",
            f"待确认操作已执行：{result.message}",
        )
        return self._to_read(updated)

    def _execute_confirmed(self, row: sqlite3.Row) -> CodeExecutionResult:
        tool = self._get_file_tool()
        payload = self._loads(row["payload_json"])
        operation_type = row["operation_type"]
        owner_username = row["owner_username"]
        conversation_id = row["conversation_id"]
        agent_name = row["agent_name"]
        if operation_type == "delete_path":
            return tool.delete_path(
                path=str(payload.get("path") or ""),
                recursive=bool(payload.get("recursive", False)),
                owner_username=owner_username,
                conversation_id=conversation_id,
                agent_name=agent_name,
                confirmed=True,
            )
        if operation_type == "run_allowed_command":
            return tool.run_allowed_command(
                command=str(payload.get("command") or ""),
                args=list(payload.get("args") or []),
                timeout_seconds=payload.get("timeout_seconds"),
                owner_username=owner_username,
                conversation_id=conversation_id,
                agent_name=agent_name,
                confirmed=True,
            )
        return CodeExecutionResult(
            status="failed",
            message="不支持确认执行该类型的 code agent 操作。",
            data={"operation_type": operation_type},
        )

    def _get_file_tool(self) -> CodeAgentFileTool:
        if isinstance(self.file_tool, CodeAgentFileTool):
            return self.file_tool
        from app.services.code_execution_service import CodeExecutionService

        self.file_tool = CodeAgentFileTool(CodeExecutionService())
        return self.file_tool

    @staticmethod
    def _to_read(row: sqlite3.Row) -> CodeOperationRead:
        return CodeOperationRead(
            operation_id=row["id"],
            conversation_id=row["conversation_id"],
            agent_name=row["agent_name"],
            operation_type=row["operation_type"],
            status=row["status"],
            payload=CodeOperationService._loads(row["payload_json"]),
            result=CodeOperationResult.model_validate(CodeOperationService._loads(row["result_json"]))
            if row["result_json"]
            else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            expires_at=row["expires_at"],
        )

    @staticmethod
    def _loads(value: str | None) -> dict:
        if not value:
            return {}
        loaded = json.loads(value)
        return loaded if isinstance(loaded, dict) else {}

    @staticmethod
    def _is_expired(value: str) -> bool:
        expires_at = datetime.fromisoformat(value)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at <= datetime.now(timezone.utc)
