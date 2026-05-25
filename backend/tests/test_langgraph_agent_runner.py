import pytest
import importlib.util
import os

from app.services.agent_runner import AgentRequest
from app.services.agent_runner_factory import create_default_agent_runner
from app.services.langgraph_agent_runner import (
    LangGraphAgentRunner,
    MissingAgentDependencyError,
    create_langgraph_agent_runner,
)
from app.services.rag_service import RagService


class FakeGraph:
    def __init__(self) -> None:
        self.payloads: list[dict] = []
        self.configs: list[dict] = []

    def invoke(self, payload: dict, config: dict | None = None) -> dict:
        self.payloads.append(payload)
        self.configs.append(config or {})
        return {
            "answer": f"graph answer: {payload['messages'][0]['content']}",
            "sources": [{"file_name": "manual.pdf"}],
            "data": {"ok": True},
            "route": "langgraph",
        }


class FakeMessagesGraph:
    def invoke(self, payload: dict, config: dict | None = None) -> dict:
        return {
            "messages": [
                {"role": "user", "content": payload["messages"][0]["content"]},
                {"role": "assistant", "content": "assistant answer"},
            ]
        }


class FakeMessageObject:
    def __init__(self, content):
        self.content = content


def test_langgraph_runner_invokes_injected_graph_factory() -> None:
    graph = FakeGraph()
    runner = LangGraphAgentRunner(graph_factory=lambda: graph)

    response = runner.run(
        AgentRequest(
            owner_username="alice",
            conversation_id="conv-1",
            message="hello",
            use_knowledge_base=True,
        )
    )

    assert response.answer == "graph answer: hello"
    assert response.sources == [{"file_name": "manual.pdf"}]
    assert response.data == {"ok": True}
    assert response.route == "langgraph"
    assert graph.payloads[0]["owner_username"] == "alice"
    assert graph.payloads[0]["conversation_id"] == "conv-1"
    assert graph.payloads[0]["agent_name"] == "main_agent"
    assert "api_key" not in graph.payloads[0]
    assert graph.payloads[0]["messages"] == [{"role": "user", "content": "hello"}]
    assert graph.configs[0] == {
        "configurable": {
            "thread_id": "alice:conv-1:main_agent",
            "checkpoint_ns": "seki-agent",
        }
    }


def test_langgraph_runner_uses_agent_name_for_context_isolation() -> None:
    graph = FakeGraph()
    runner = LangGraphAgentRunner(graph_factory=lambda: graph)

    runner.run(
        AgentRequest(
            owner_username="alice",
            conversation_id="conv-1",
            message="write code",
            agent_name="code_agent",
        )
    )

    assert graph.configs[0]["configurable"]["thread_id"] == "alice:conv-1:code_agent"
    assert graph.payloads[0]["agent_name"] == "code_agent"


def test_langgraph_runner_can_build_graph_from_request_context() -> None:
    graphs: dict[str, FakeGraph] = {}

    def graph_factory(request: AgentRequest) -> FakeGraph:
        graph = FakeGraph()
        graphs[request.owner_username] = graph
        return graph

    runner = LangGraphAgentRunner(graph_factory=graph_factory)

    response = runner.run(
        AgentRequest(
            owner_username="alice",
            conversation_id="conv-1",
            message="hello",
            use_knowledge_base=True,
        )
    )

    assert response.answer == "graph answer: hello"
    assert set(graphs) == {"alice"}
    assert graphs["alice"].payloads[0]["owner_username"] == "alice"


def test_langgraph_runner_includes_agent_state_metadata_in_data() -> None:
    response = LangGraphAgentRunner._to_response(
        {
            "answer": "code boundary",
            "route": "code_agent",
            "agent_name": "code_agent",
            "active_agent": "code_agent",
        }
    )

    assert response.data == {
        "agent_name": "code_agent",
        "active_agent": "code_agent",
    }


def test_langgraph_runner_uses_request_api_key_temporarily_when_env_is_missing(monkeypatch) -> None:
    monkeypatch.delenv("SEKI_RAG_API_KEY", raising=False)
    seen_api_keys: list[str | None] = []

    class KeyReadingGraph:
        def invoke(self, payload: dict, config: dict | None = None) -> dict:
            seen_api_keys.append(os.environ.get("SEKI_RAG_API_KEY"))
            return {"answer": "ok"}

    runner = LangGraphAgentRunner(graph_factory=KeyReadingGraph)

    runner.run(
        AgentRequest(
            owner_username="alice",
            conversation_id="conv-1",
            message="hello",
            api_key="request-key",
        )
    )

    assert seen_api_keys == ["request-key"]
    assert "SEKI_RAG_API_KEY" not in os.environ


def test_langgraph_runner_extracts_answer_from_messages_result() -> None:
    runner = LangGraphAgentRunner(graph_factory=FakeMessagesGraph)

    response = runner.run(
        AgentRequest(
            owner_username="alice",
            conversation_id="conv-1",
            message="hello",
        )
    )

    assert response.answer == "assistant answer"


def test_langgraph_runner_extracts_current_turn_tool_messages() -> None:
    response = LangGraphAgentRunner._to_response(
        {
            "messages": [
                {"role": "user", "content": "old"},
                {"role": "tool", "content": "old tool"},
                {"role": "assistant", "content": "old answer"},
                {"role": "user", "content": "new"},
                {"role": "tool", "content": "new tool"},
                {"role": "assistant", "content": "new answer"},
            ],
        }
    )

    assert response.answer == "new answer"
    assert [(item.role, item.content) for item in response.messages_to_store] == [("tool", "new tool")]


def test_langgraph_runner_extracts_answer_from_message_object_content_list() -> None:
    response = LangGraphAgentRunner._to_response(
        {
            "messages": [
                FakeMessageObject("human"),
                FakeMessageObject([{"text": "assistant"}, {"content": "answer"}]),
            ]
        }
    )

    assert response.answer == "assistant\nanswer"


def test_create_langgraph_runner_reports_missing_dependencies() -> None:
    if all(importlib.util.find_spec(module) for module in ("langgraph", "langchain", "langchain_openai")):
        pytest.skip("LangGraph dependencies are installed in this environment")

    with pytest.raises(MissingAgentDependencyError):
        create_langgraph_agent_runner()


def test_default_runner_uses_langgraph_boundary() -> None:
    runner = create_default_agent_runner(
        RagService(answerer=lambda question: {"answer": f"rag: {question}", "sources": []}),
    )

    assert isinstance(runner, LangGraphAgentRunner)
