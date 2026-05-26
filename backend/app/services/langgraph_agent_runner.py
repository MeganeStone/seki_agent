from collections.abc import Callable
from hashlib import sha1
from typing import Any

from app.core.api_keys import temporary_env_api_key
from app.services.agent_prompts import TBOX_AGENT_SYSTEM_PROMPT
from app.services.agent_runner import AgentRequest, AgentResponse, AgentRunner, ChatHistoryMessage


class MissingAgentDependencyError(RuntimeError):
    pass


class LangGraphAgentRunner:
    """LangGraph runner 边界。

    AgentService 只依赖 AgentRunner 协议，不直接 import LangGraph。这里负责把
    后端的 AgentRequest 转成 LangGraph 可识别的 messages/config，再把 graph
    返回结果转成统一的 AgentResponse。
    """

    def __init__(
        self,
        graph_factory: Callable[[], object] | Callable[[AgentRequest], object],
        system_prompt: str = TBOX_AGENT_SYSTEM_PROMPT,
    ):
        self.graph_factory = graph_factory
        self.system_prompt = system_prompt
        self._graph = None

    def run(self, request: AgentRequest) -> AgentResponse:
        """调用 LangGraph graph。

        thread_id 使用 `用户:会话` 组合，让 LangSmith 和 LangGraph checkpoint 把同一个
        conversation 归为同一条 thread；主/子 Agent 的消息隔离在父图 handoff 和子图
        state 清洗中完成。
        """
        graph = self._get_graph(request)
        agent_histories = request.agent_histories or {request.agent_name: request.history}
        history_messages = LangGraphAgentRunner._history_messages_for_graph(
            agent_histories.get(request.agent_name, request.history)[-20:]
        )
        payload = {
            "owner_username": request.owner_username,
            "conversation_id": request.conversation_id,
            "agent_name": request.agent_name,
            "active_agent": request.agent_name,
            "messages": history_messages + [{"role": "user", "content": request.message}],
            "main_agent_messages": LangGraphAgentRunner._history_messages_for_graph(
                agent_histories.get("main_agent", ())[-20:]
            ),
            "code_agent_messages": LangGraphAgentRunner._history_messages_for_graph(
                agent_histories.get("code_agent", ())[-20:]
            ),
            "system_prompt": self.system_prompt,
            "use_knowledge_base": request.use_knowledge_base,
        }
        config = {
            "configurable": {
                "thread_id": f"{request.owner_username}:{request.conversation_id}",
                "checkpoint_ns": "seki-agent",
            }
        }
        with temporary_env_api_key("SEKI_RAG_API_KEY", request.api_key):
            result = graph.invoke(payload, config=config)
        return self._to_response(result)

    def _get_graph(self, request: AgentRequest):
        """按用户会话懒创建 graph 实例，避免所有会话共享同一个内存 checkpointer。"""
        if self._graph is None:
            self._graph = {}
        key = f"{request.owner_username}:{request.conversation_id}"
        if isinstance(self._graph, dict) and key not in self._graph:
            try:
                self._graph[key] = self.graph_factory(request)
            except TypeError:
                self._graph[key] = self.graph_factory()
        if isinstance(self._graph, dict):
            return self._graph[key]
        return self._graph

    @staticmethod
    def _to_response(result: object) -> AgentResponse:
        """兼容 dict、AgentResponse 和普通对象三类 graph 返回值。"""
        if isinstance(result, AgentResponse):
            return result
        if isinstance(result, dict):
            answer = result.get("answer")
            if answer is None:
                answer = LangGraphAgentRunner._extract_last_message_content(result.get("messages", []))
            return AgentResponse(
                answer=str(answer or ""),
                sources=result.get("sources", []),
                data=LangGraphAgentRunner._response_data(result),
                route=str(result.get("route", "langgraph")),
                messages_to_store=LangGraphAgentRunner._extract_messages_to_store(result.get("messages", [])),
            )
        return AgentResponse(answer=str(result), route="langgraph")

    @staticmethod
    def _response_data(result: dict) -> dict | None:
        data = result.get("data")
        if data is None:
            data = {}
        if not isinstance(data, dict):
            data = {"value": data}

        for key in ("agent_name", "active_agent"):
            if key in result and key not in data:
                data[key] = result[key]

        return data or None

    @staticmethod
    def _extract_last_message_content(messages: object) -> str:
        if not isinstance(messages, list):
            return ""

        for message in reversed(messages):
            content = LangGraphAgentRunner._message_content(message)
            if content:
                return content
        return ""

    @staticmethod
    def _message_content(message: object) -> str:
        if isinstance(message, dict):
            content = message.get("content")
        else:
            content = getattr(message, "content", None)

        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if isinstance(text, str):
                        parts.append(text)
            return "\n".join(parts)
        return ""

    @staticmethod
    def _history_messages_for_graph(history: tuple[ChatHistoryMessage, ...]) -> list[dict]:
        """Build LangGraph replay history, including persisted AI tool-call pairs."""
        messages: list[dict] = []
        for index, item in enumerate(history):
            if item.role not in {"user", "assistant", "tool"}:
                continue
            metadata = item.metadata or {}
            if not item.content.strip() and not metadata.get("tool_calls"):
                continue
            if item.role == "assistant":
                message = {"role": "assistant", "content": item.content}
                tool_calls = metadata.get("tool_calls")
                if isinstance(tool_calls, list) and tool_calls:
                    message["tool_calls"] = tool_calls
                messages.append(message)
                continue
            if item.role == "tool":
                tool_call_id = metadata.get("tool_call_id")
                if not isinstance(tool_call_id, str) or not tool_call_id:
                    digest = sha1(item.content.encode("utf-8")).hexdigest()[:12]
                    tool_call_id = f"history-{index}-{digest}"
                    messages.append(
                        {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": tool_call_id,
                                    "name": metadata.get("tool_name") or "historical_tool",
                                    "args": {},
                                    "type": "tool_call",
                                }
                            ],
                        }
                    )
                tool_message = {
                    "role": "tool",
                    "content": item.content,
                    "tool_call_id": tool_call_id,
                }
                tool_name = metadata.get("tool_name")
                if isinstance(tool_name, str) and tool_name:
                    tool_message["name"] = tool_name
                messages.append(tool_message)
                continue
            messages.append({"role": item.role, "content": item.content})
        return messages

    @staticmethod
    def _message_metadata(message: object) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        if isinstance(message, dict):
            tool_calls = message.get("tool_calls")
            if isinstance(tool_calls, list) and tool_calls:
                metadata["tool_calls"] = tool_calls
            tool_call_id = message.get("tool_call_id")
            if isinstance(tool_call_id, str) and tool_call_id:
                metadata["tool_call_id"] = tool_call_id
            tool_name = message.get("name") or message.get("tool_name")
            if isinstance(tool_name, str) and tool_name:
                metadata["tool_name"] = tool_name
            return metadata

        tool_calls = getattr(message, "tool_calls", None)
        if isinstance(tool_calls, list) and tool_calls:
            metadata["tool_calls"] = tool_calls
        tool_call_id = getattr(message, "tool_call_id", None)
        if isinstance(tool_call_id, str) and tool_call_id:
            metadata["tool_call_id"] = tool_call_id
        tool_name = getattr(message, "name", None) or getattr(message, "tool_name", None)
        if isinstance(tool_name, str) and tool_name:
            metadata["tool_name"] = tool_name
        return metadata

    @staticmethod
    def _extract_messages_to_store(messages: object) -> tuple[ChatHistoryMessage, ...]:
        if not isinstance(messages, list):
            return ()

        last_user_index = -1
        for index, message in enumerate(messages):
            if LangGraphAgentRunner._message_role(message) in {"user", "human"}:
                last_user_index = index

        current_turn = messages[last_user_index + 1 :] if last_user_index >= 0 else messages
        stored: list[ChatHistoryMessage] = []
        pending_ai_by_id: dict[str, ChatHistoryMessage] = {}
        stored_ai_ids: set[str] = set()

        for message in current_turn:
            role = LangGraphAgentRunner._message_role(message)
            metadata = LangGraphAgentRunner._message_metadata(message)
            if role in {"assistant", "ai"} and metadata.get("tool_calls"):
                ai_message = ChatHistoryMessage(
                    role="assistant",
                    content=LangGraphAgentRunner._message_content(message),
                    metadata=metadata,
                )
                for tool_call in metadata["tool_calls"]:
                    if not isinstance(tool_call, dict):
                        continue
                    tool_call_id = tool_call.get("id")
                    if isinstance(tool_call_id, str) and tool_call_id:
                        pending_ai_by_id[tool_call_id] = ai_message
                continue

            if role != "tool":
                continue

            content = LangGraphAgentRunner._message_content(message)
            if not content:
                continue
            tool_call_id = metadata.get("tool_call_id")
            if isinstance(tool_call_id, str) and tool_call_id in pending_ai_by_id and tool_call_id not in stored_ai_ids:
                stored.append(pending_ai_by_id[tool_call_id])
                stored_ai_ids.add(tool_call_id)
            stored.append(ChatHistoryMessage(role="tool", content=content, metadata=metadata or None))

        return tuple(stored)

    @staticmethod
    def _message_role(message: object) -> str:
        if isinstance(message, dict):
            role = message.get("role") or message.get("type")
        else:
            role = getattr(message, "role", None) or getattr(message, "type", None)
            if role is None and message.__class__.__name__ == "ToolMessage":
                role = "tool"
        return str(role or "").lower()


def create_langgraph_agent_runner(graph_factory: Callable[[], object] | None = None) -> AgentRunner:
    if graph_factory is not None:
        return LangGraphAgentRunner(graph_factory=graph_factory)

    try:
        import langgraph  # noqa: F401
        import langchain  # noqa: F401
        import langchain_openai  # noqa: F401
    except ImportError as exc:
        raise MissingAgentDependencyError(
            "LangGraph Agent runner requires langgraph, langchain and langchain-openai"
        ) from exc

    raise NotImplementedError("LangGraph graph factory has not been implemented yet")
