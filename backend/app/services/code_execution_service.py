from dataclasses import dataclass, field
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
import subprocess
import sys
import shutil
from uuid import uuid4

from app.core.config import get_settings


@dataclass(frozen=True)
class CodeExecutionResult:
    status: str
    message: str
    data: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CodeOperationRecord:
    operation_id: str
    owner_username: str
    conversation_id: str
    agent_name: str
    tool_name: str
    status: str
    target: str
    message: str
    started_at: datetime
    finished_at: datetime


@dataclass(frozen=True)
class CommandPolicyDecision:
    status: str
    message: str
    executable: list[str] = field(default_factory=list)
    requires_confirmation: bool = False


class CodeExecutionService:
    """Restricted local file service for the code agent stage A.

    Stage A intentionally does not expose shell execution or deletion. It only
    supports listing directories, reading small text files, and writing text
    files with explicit overwrite.
    """

    def __init__(
        self,
        allowed_roots: list[Path] | None = None,
        default_root: Path | None = None,
        max_read_bytes: int | None = None,
        max_write_bytes: int | None = None,
        max_output_chars: int = 8000,
        default_timeout_seconds: int = 30,
        blocked_name_patterns: list[str] | None = None,
    ):
        settings = get_settings()
        roots = allowed_roots or settings.code_agent_allowed_roots or [
            settings.project_root,
            settings.workspace_dir,
            settings.skills_dir,
        ]
        self.allowed_roots = [root.resolve() for root in roots]
        self.default_root = (default_root or self.allowed_roots[0]).resolve()
        self.max_read_bytes = max_read_bytes or settings.code_agent_max_read_bytes
        self.max_write_bytes = max_write_bytes or settings.code_agent_max_write_bytes
        self.max_output_chars = max_output_chars
        self.default_timeout_seconds = default_timeout_seconds
        self.blocked_name_patterns = blocked_name_patterns or [
            ".env",
            ".env.*",
            "*.pem",
            "*.key",
            "*.p12",
            "*.pfx",
            "id_rsa",
            "id_ed25519",
            "*.sqlite",
            "*.sqlite3",
            "*.db",
        ]
        self.audit_records: list[CodeOperationRecord] = []
        self.created_paths: set[Path] = set()
        if not self._is_under_allowed_root(self.default_root):
            raise ValueError("default_root must be under an allowed root")
        self.command_policy = CommandPolicy(
            python_executable=sys.executable,
            allowed_prefixes=settings.code_agent_allowed_command_prefixes,
            confirmed_prefixes=settings.code_agent_confirmed_command_prefixes,
        )

    def list_dir(
        self,
        path: str = ".",
        limit: int = 100,
        owner_username: str = "",
        conversation_id: str = "",
        agent_name: str = "code_agent",
    ) -> CodeExecutionResult:
        started_at = self._now()
        target = ""
        try:
            resolved = self._resolve_existing_path(path)
            target = self._display_path(resolved)
            if not resolved.is_dir():
                return self._record_result(
                    "list_dir",
                    "failed",
                    target,
                    "目标路径不是目录。",
                    started_at,
                    owner_username,
                    conversation_id,
                    agent_name,
                )

            safe_limit = max(1, min(limit, 500))
            all_entries = sorted(resolved.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
            entries = all_entries[:safe_limit]
            items = [
                {
                    "name": item.name,
                    "path": self._display_path(item),
                    "type": "dir" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else None,
                }
                for item in entries
            ]
            return self._record_result(
                "list_dir",
                "succeeded",
                target,
                f"列出 {len(items)} 个条目。",
                started_at,
                owner_username,
                conversation_id,
                agent_name,
                data={"items": items, "truncated": len(all_entries) > safe_limit},
            )
        except ValueError as exc:
            return self._record_result(
                "list_dir",
                "rejected",
                target or path,
                str(exc),
                started_at,
                owner_username,
                conversation_id,
                agent_name,
            )

    def create_dir(
        self,
        path: str,
        owner_username: str = "",
        conversation_id: str = "",
        agent_name: str = "code_agent",
    ) -> CodeExecutionResult:
        started_at = self._now()
        target = ""
        try:
            resolved = self._resolve_writable_path(path)
            target = self._display_path(resolved)
            if resolved.exists():
                if resolved.is_dir():
                    status = "succeeded"
                    message = "目录已存在。"
                else:
                    status = "failed"
                    message = "目标路径已存在且不是目录。"
                return self._record_result(
                    "create_dir",
                    status,
                    target,
                    message,
                    started_at,
                    owner_username,
                    conversation_id,
                    agent_name,
                    data={
                        "path": path,
                        "recursive": recursive,
                        "requires_confirmation": True,
                    },
                )

            resolved.mkdir()
            self.created_paths.add(resolved)
            return self._record_result(
                "create_dir",
                "succeeded",
                target,
                "目录创建成功。",
                started_at,
                owner_username,
                conversation_id,
                agent_name,
            )
        except ValueError as exc:
            return self._record_result(
                "create_dir",
                "rejected",
                target or path,
                str(exc),
                started_at,
                owner_username,
                conversation_id,
                agent_name,
            )

    def delete_path(
        self,
        path: str,
        recursive: bool = False,
        owner_username: str = "",
        conversation_id: str = "",
        agent_name: str = "code_agent",
        confirmed: bool = False,
    ) -> CodeExecutionResult:
        started_at = self._now()
        target = ""
        try:
            resolved = self._resolve_existing_path(path)
            target = self._display_path(resolved)
            if not confirmed and not self._is_agent_created_path(resolved):
                return self._record_result(
                    "delete_path",
                    "requires_confirmation",
                    target,
                    "该路径不是 code agent 本次运行创建的内容，删除前需要用户确认。",
                    started_at,
                    owner_username,
                    conversation_id,
                    agent_name,
                    data={
                        "path": path,
                        "recursive": recursive,
                        "requires_confirmation": True,
                    },
                )

            if resolved.is_dir():
                if not recursive:
                    return self._record_result(
                        "delete_path",
                        "rejected",
                        target,
                        "删除目录需要显式 recursive=true。",
                        started_at,
                        owner_username,
                        conversation_id,
                        agent_name,
                    )
                shutil.rmtree(resolved)
                self._forget_created_path(resolved)
                return self._record_result(
                    "delete_path",
                    "succeeded",
                    target,
                    "目录删除成功。",
                    started_at,
                    owner_username,
                    conversation_id,
                    agent_name,
                    data={"recursive": recursive},
                )

            if resolved.is_file():
                resolved.unlink()
                self._forget_created_path(resolved)
                return self._record_result(
                    "delete_path",
                    "succeeded",
                    target,
                    "文件删除成功。",
                    started_at,
                    owner_username,
                    conversation_id,
                    agent_name,
                )

            return self._record_result(
                "delete_path",
                "rejected",
                target,
                "当前只允许删除普通文件或目录。",
                started_at,
                owner_username,
                conversation_id,
                agent_name,
            )
        except ValueError as exc:
            return self._record_result(
                "delete_path",
                "rejected",
                target or path,
                str(exc),
                started_at,
                owner_username,
                conversation_id,
                agent_name,
            )

    def run_python_script(
        self,
        path: str,
        args: list[str] | None = None,
        timeout_seconds: int | None = None,
        owner_username: str = "",
        conversation_id: str = "",
        agent_name: str = "code_agent",
    ) -> CodeExecutionResult:
        started_at = self._now()
        target = ""
        try:
            resolved = self._resolve_existing_path(path)
            target = self._display_path(resolved)
            if not resolved.is_file():
                return self._record_result(
                    "run_python_script",
                    "failed",
                    target,
                    "目标路径不是文件。",
                    started_at,
                    owner_username,
                    conversation_id,
                    agent_name,
                )
            if resolved.suffix.lower() != ".py":
                return self._record_result(
                    "run_python_script",
                    "rejected",
                    target,
                    "当前只允许运行 .py 脚本。",
                    started_at,
                    owner_username,
                    conversation_id,
                    agent_name,
                )

            clean_args = [str(arg) for arg in (args or [])]
            timeout = max(1, min(timeout_seconds or self.default_timeout_seconds, self.default_timeout_seconds))
            completed = subprocess.run(
                [sys.executable, str(resolved), *clean_args],
                cwd=str(resolved.parent),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
            stdout, stdout_truncated = self._truncate_output(completed.stdout)
            stderr, stderr_truncated = self._truncate_output(completed.stderr)
            status = "succeeded" if completed.returncode == 0 else "failed"
            message = "Python 脚本执行完成。" if status == "succeeded" else "Python 脚本执行失败。"
            return self._record_result(
                "run_python_script",
                status,
                target,
                message,
                started_at,
                owner_username,
                conversation_id,
                agent_name,
                data={
                    "returncode": completed.returncode,
                    "stdout": stdout,
                    "stderr": stderr,
                    "stdout_truncated": stdout_truncated,
                    "stderr_truncated": stderr_truncated,
                    "timeout_seconds": timeout,
                    "args": clean_args,
                },
            )
        except subprocess.TimeoutExpired as exc:
            stdout, stdout_truncated = self._truncate_output(_timeout_output_to_text(exc.stdout))
            stderr, stderr_truncated = self._truncate_output(_timeout_output_to_text(exc.stderr))
            return self._record_result(
                "run_python_script",
                "failed",
                target or path,
                "Python 脚本执行超时。",
                started_at,
                owner_username,
                conversation_id,
                agent_name,
                data={
                    "stdout": stdout,
                    "stderr": stderr,
                    "stdout_truncated": stdout_truncated,
                    "stderr_truncated": stderr_truncated,
                    "timeout_seconds": timeout_seconds or self.default_timeout_seconds,
                },
            )
        except ValueError as exc:
            return self._record_result(
                "run_python_script",
                "rejected",
                target or path,
                str(exc),
                started_at,
                owner_username,
                conversation_id,
                agent_name,
            )

    def run_allowed_command(
        self,
        command: str,
        args: list[str] | None = None,
        timeout_seconds: int | None = None,
        owner_username: str = "",
        conversation_id: str = "",
        agent_name: str = "code_agent",
        confirmed: bool = False,
    ) -> CodeExecutionResult:
        started_at = self._now()
        clean_args = [str(arg) for arg in (args or [])]
        decision = self.command_policy.evaluate(command, clean_args)
        target = " ".join([command, *clean_args]).strip()
        if decision.status == "requires_confirmation" and confirmed and decision.requires_confirmation:
            pass
        elif decision.status == "requires_confirmation" and confirmed:
            return self._record_result(
                "run_allowed_command",
                "failed",
                target,
                "该命令已确认，但未匹配确认后可执行的配置前缀。",
                started_at,
                owner_username,
                conversation_id,
                agent_name,
                data={
                    "command": command,
                    "args": clean_args,
                    "requires_confirmation": False,
                    "confirmed": True,
                },
            )
        elif decision.status != "allow":
            data = {
                "command": command,
                "args": clean_args,
                "requires_confirmation": decision.status == "requires_confirmation",
            }
            if decision.requires_confirmation:
                data["policy"] = "confirmed_prefix"
            return self._record_result(
                "run_allowed_command",
                decision.status,
                target,
                decision.message,
                started_at,
                owner_username,
                conversation_id,
                agent_name,
                data=data,
            )

        if decision.requires_confirmation and not confirmed:
            return self._record_result(
                "run_allowed_command",
                "requires_confirmation",
                target,
                "该命令需要用户确认后执行。",
                started_at,
                owner_username,
                conversation_id,
                agent_name,
                data={
                    "command": command,
                    "args": clean_args,
                    "requires_confirmation": True,
                    "policy": "confirmed_prefix",
                },
            )

        timeout = max(1, min(timeout_seconds or self.default_timeout_seconds, self.default_timeout_seconds))
        try:
            completed = subprocess.run(
                decision.executable,
                cwd=str(self.default_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
            stdout, stdout_truncated = self._truncate_output(completed.stdout)
            stderr, stderr_truncated = self._truncate_output(completed.stderr)
            status = "succeeded" if completed.returncode == 0 else "failed"
            message = "命令执行完成。" if status == "succeeded" else "命令执行失败。"
            return self._record_result(
                "run_allowed_command",
                status,
                target,
                message,
                started_at,
                owner_username,
                conversation_id,
                agent_name,
                data={
                    "returncode": completed.returncode,
                    "stdout": stdout,
                    "stderr": stderr,
                    "stdout_truncated": stdout_truncated,
                    "stderr_truncated": stderr_truncated,
                    "timeout_seconds": timeout,
                    "command": command,
                    "args": clean_args,
                },
            )
        except FileNotFoundError:
            return self._record_result(
                "run_allowed_command",
                "failed",
                target,
                "命令不可用或未安装。",
                started_at,
                owner_username,
                conversation_id,
                agent_name,
            )
        except subprocess.TimeoutExpired as exc:
            stdout, stdout_truncated = self._truncate_output(_timeout_output_to_text(exc.stdout))
            stderr, stderr_truncated = self._truncate_output(_timeout_output_to_text(exc.stderr))
            return self._record_result(
                "run_allowed_command",
                "failed",
                target,
                "命令执行超时。",
                started_at,
                owner_username,
                conversation_id,
                agent_name,
                data={
                    "stdout": stdout,
                    "stderr": stderr,
                    "stdout_truncated": stdout_truncated,
                    "stderr_truncated": stderr_truncated,
                    "timeout_seconds": timeout,
                    "command": command,
                    "args": clean_args,
                },
            )

    def read_text_file(
        self,
        path: str,
        max_bytes: int | None = None,
        owner_username: str = "",
        conversation_id: str = "",
        agent_name: str = "code_agent",
    ) -> CodeExecutionResult:
        started_at = self._now()
        target = ""
        try:
            resolved = self._resolve_existing_path(path)
            target = self._display_path(resolved)
            if not resolved.is_file():
                return self._record_result(
                    "read_text_file",
                    "failed",
                    target,
                    "目标路径不是文件。",
                    started_at,
                    owner_username,
                    conversation_id,
                    agent_name,
                )

            byte_limit = min(max_bytes or self.max_read_bytes, self.max_read_bytes)
            size = resolved.stat().st_size
            if size > byte_limit:
                return self._record_result(
                    "read_text_file",
                    "rejected",
                    target,
                    "文件超过当前读取限制。",
                    started_at,
                    owner_username,
                    conversation_id,
                    agent_name,
                    data={"size": size, "max_bytes": byte_limit},
                )

            content = resolved.read_text(encoding="utf-8")
            return self._record_result(
                "read_text_file",
                "succeeded",
                target,
                "文件读取成功。",
                started_at,
                owner_username,
                conversation_id,
                agent_name,
                data={"content": content, "size": size},
            )
        except UnicodeDecodeError:
            return self._record_result(
                "read_text_file",
                "failed",
                target or path,
                "文件不是 UTF-8 文本，当前只支持读取文本文件。",
                started_at,
                owner_username,
                conversation_id,
                agent_name,
            )
        except ValueError as exc:
            return self._record_result(
                "read_text_file",
                "rejected",
                target or path,
                str(exc),
                started_at,
                owner_username,
                conversation_id,
                agent_name,
            )

    def write_text_file(
        self,
        path: str,
        content: str,
        overwrite: bool = False,
        owner_username: str = "",
        conversation_id: str = "",
        agent_name: str = "code_agent",
    ) -> CodeExecutionResult:
        started_at = self._now()
        target = ""
        try:
            encoded = content.encode("utf-8")
            if len(encoded) > self.max_write_bytes:
                return self._record_result(
                    "write_text_file",
                    "rejected",
                    path,
                    "写入内容超过当前大小限制。",
                    started_at,
                    owner_username,
                    conversation_id,
                    agent_name,
                    data={"size": len(encoded), "max_bytes": self.max_write_bytes},
                )

            resolved = self._resolve_writable_path(path)
            target = self._display_path(resolved)
            if resolved.exists() and not overwrite:
                return self._record_result(
                    "write_text_file",
                    "rejected",
                    target,
                    "目标文件已存在，覆盖写入需要显式 overwrite=true。",
                    started_at,
                    owner_username,
                    conversation_id,
                    agent_name,
                )
            if resolved.exists() and not resolved.is_file():
                return self._record_result(
                    "write_text_file",
                    "failed",
                    target,
                    "目标路径不是文件。",
                    started_at,
                    owner_username,
                    conversation_id,
                    agent_name,
                )

            resolved.write_text(content, encoding="utf-8")
            if not overwrite:
                self.created_paths.add(resolved)
            return self._record_result(
                "write_text_file",
                "succeeded",
                target,
                "文件写入成功。",
                started_at,
                owner_username,
                conversation_id,
                agent_name,
                data={"size": len(encoded), "overwrite": overwrite},
            )
        except ValueError as exc:
            return self._record_result(
                "write_text_file",
                "rejected",
                target or path,
                str(exc),
                started_at,
                owner_username,
                conversation_id,
                agent_name,
            )

    def _resolve_existing_path(self, path: str) -> Path:
        resolved = self._candidate_path(path).resolve()
        self._ensure_allowed(resolved)
        if not resolved.exists():
            raise ValueError("路径不存在。")
        self._reject_symlink_path(resolved)
        self._reject_sensitive_path(resolved)
        return resolved

    def _resolve_writable_path(self, path: str) -> Path:
        candidate = self._candidate_path(path)
        parent = candidate.parent.resolve()
        self._ensure_allowed(parent)
        if not parent.exists() or not parent.is_dir():
            raise ValueError("父目录不存在或不是目录。")
        self._reject_symlink_path(parent)
        self._reject_sensitive_path(parent)
        resolved = candidate.resolve()
        self._ensure_allowed(resolved)
        if resolved.exists():
            self._reject_symlink_path(resolved)
        self._reject_sensitive_path(resolved)
        return resolved

    def _candidate_path(self, path: str) -> Path:
        if not path.strip():
            raise ValueError("路径不能为空。")
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.default_root / candidate
        return candidate

    def _ensure_allowed(self, resolved: Path) -> None:
        if not self._is_under_allowed_root(resolved):
            raise ValueError("该路径不在允许的工作目录内。")

    def _is_under_allowed_root(self, resolved: Path) -> bool:
        return any(root == resolved or root in resolved.parents for root in self.allowed_roots)

    def _reject_symlink_path(self, resolved: Path) -> None:
        for root in self.allowed_roots:
            if root == resolved or root in resolved.parents:
                relative_parts = resolved.relative_to(root).parts
                current = root
                for part in relative_parts:
                    current = current / part
                    if current.exists() and current.is_symlink():
                        raise ValueError("当前阶段不允许通过符号链接访问文件。")
                return

    def _reject_sensitive_path(self, resolved: Path) -> None:
        for part in resolved.parts:
            if any(fnmatch(part, pattern) for pattern in self.blocked_name_patterns):
                raise ValueError("当前阶段不允许 code agent 访问敏感文件。")

    def _display_path(self, path: Path) -> str:
        resolved = path.resolve()
        for root in self.allowed_roots:
            if root == resolved or root in resolved.parents:
                return str(resolved.relative_to(root)).replace("\\", "/") or "."
        return resolved.name

    def _truncate_output(self, value: str | None) -> tuple[str, bool]:
        text = value or ""
        if len(text) <= self.max_output_chars:
            return text, False
        return text[: self.max_output_chars], True

    def _is_agent_created_path(self, resolved: Path) -> bool:
        return any(created == resolved or created in resolved.parents for created in self.created_paths)

    def _forget_created_path(self, resolved: Path) -> None:
        self.created_paths = {
            created
            for created in self.created_paths
            if not (created == resolved or resolved in created.parents)
        }

    def _record_result(
        self,
        tool_name: str,
        status: str,
        target: str,
        message: str,
        started_at: datetime,
        owner_username: str,
        conversation_id: str,
        agent_name: str,
        data: dict | None = None,
    ) -> CodeExecutionResult:
        finished_at = self._now()
        operation_id = uuid4().hex
        payload = {
            "operation_id": operation_id,
            "operation_type": tool_name,
            "target": target,
            **(data or {}),
        }
        self.audit_records.append(
            CodeOperationRecord(
                operation_id=operation_id,
                owner_username=owner_username,
                conversation_id=conversation_id,
                agent_name=agent_name,
                tool_name=tool_name,
                status=status,
                target=target,
                message=message,
                started_at=started_at,
                finished_at=finished_at,
            )
        )
        return CodeExecutionResult(status=status, message=message, data=payload)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)


def _timeout_output_to_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


class CommandPolicy:
    def __init__(
        self,
        python_executable: str,
        allowed_prefixes: list[str] | None = None,
        confirmed_prefixes: list[str] | None = None,
    ):
        self.python_executable = python_executable
        self.allowed_prefixes = [_split_prefix(prefix) for prefix in (allowed_prefixes or []) if prefix.strip()]
        self.confirmed_prefixes = [_split_prefix(prefix) for prefix in (confirmed_prefixes or []) if prefix.strip()]
        self.denied_tokens = {
            "rm",
            "del",
            "remove-item",
            "rmdir",
            "rd",
            "mv",
            "move",
            "curl",
            "wget",
            "chmod",
            "chown",
            "sudo",
            "powershell",
            "cmd",
            "bash",
            "sh",
            "git reset",
            "git clean",
        }
        self.denied_fragments = {";", "&&", "||", "|", ">", "<", "`", "$(", "\n", "\r"}

    def evaluate(self, command: str, args: list[str]) -> CommandPolicyDecision:
        clean_command = command.strip().lower()
        if not clean_command:
            return CommandPolicyDecision("rejected", "命令不能为空。")

        joined = " ".join([clean_command, *[arg.lower() for arg in args]])
        if any(fragment in joined for fragment in self.denied_fragments):
            return CommandPolicyDecision("rejected", "命令包含未开放的 shell 控制符。")
        if any(token == clean_command or joined.startswith(f"{token} ") for token in self.denied_tokens):
            return CommandPolicyDecision("rejected", "该命令被安全策略禁止。")

        tokens = [clean_command, *args]

        allowed_prefix = self._matching_prefix(tokens, self.allowed_prefixes)
        if allowed_prefix:
            return CommandPolicyDecision("allow", "允许执行配置白名单命令。", [command.strip(), *args])

        confirmed_prefix = self._matching_prefix(tokens, self.confirmed_prefixes)
        if confirmed_prefix:
            return CommandPolicyDecision(
                "requires_confirmation",
                "该命令匹配确认后可执行前缀。",
                [command.strip(), *args],
                requires_confirmation=True,
            )

        if clean_command == "git" and args and args[0] in {"status", "diff"}:
            return CommandPolicyDecision("allow", "允许执行 git 只读命令。", ["git", *args])

        if clean_command == "pytest":
            return CommandPolicyDecision(
                "allow",
                "允许执行 pytest。",
                [self.python_executable, "-m", "pytest", *args],
            )

        if clean_command == "python" and len(args) >= 2 and args[:2] == ["-m", "pytest"]:
            return CommandPolicyDecision(
                "allow",
                "允许执行 python -m pytest。",
                [self.python_executable, "-m", "pytest", *args[2:]],
            )

        if clean_command == "npm" and args in (["run", "lint"], ["run", "build"]):
            return CommandPolicyDecision("allow", "允许执行 npm run lint/build。", ["npm", *args])

        return CommandPolicyDecision("requires_confirmation", "该命令未在白名单中，执行前需要用户确认。")

    @staticmethod
    def _matching_prefix(tokens: list[str], prefixes: list[list[str]]) -> list[str] | None:
        lowered_tokens = [token.lower() for token in tokens]
        for prefix in prefixes:
            if len(prefix) <= len(lowered_tokens) and lowered_tokens[: len(prefix)] == prefix:
                return prefix
        return None


def _split_prefix(prefix: str) -> list[str]:
    return [part.lower() for part in prefix.split() if part.strip()]
