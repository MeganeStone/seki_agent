from collections.abc import Callable

from app.core.api_keys import temporary_env_api_key
from app.services.agent_prompts import TBOX_AGENT_SYSTEM_PROMPT
from app.services.agent_runner import AgentRequest, AgentResponse, AgentRunner


class MissingAgentDependencyError(RuntimeError):
    pass


class LangGraphAgentRunner:
    """Thin LangGraph runner boundary.

    The production graph factory is injected so tests can verify this boundary
    without importing LangGraph or calling real LLMs. When dependencies are not
    installed, create_langgraph_agent_runner raises a clear error and callers can
    fall back to RuleBasedAgentRunner.
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
        graph = self._get_graph(request)
        payload = {
            "owner_username": request.owner_username,
            "conversation_id": request.conversation_id,
            "agent_name": request.agent_name,
            "messages": [{"role": "user", "content": request.message}],
            "system_prompt": self.system_prompt,
            "use_knowledge_base": request.use_knowledge_base,
        }
        config = {
            "configurable": {
                "thread_id": f"{request.owner_username}:{request.conversation_id}:{request.agent_name}",
                "checkpoint_ns": "seki-agent",
            }
        }
        with temporary_env_api_key("SEKI_RAG_API_KEY", request.api_key):
            result = graph.invoke(payload, config=config)
        return self._to_response(result)

    def _get_graph(self, request: AgentRequest):
        if self._graph is None:
            self._graph = {}
        key = f"{request.owner_username}:{request.conversation_id}:{request.agent_name}"
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
