import pytest
import importlib.util

from app.services.agent_runner import AgentRequest
from app.services.agent_runner_factory import create_default_agent_runner
from app.services.agent_tools import RagAgentTool
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
    assert graph.payloads[0]["messages"] == [{"role": "user", "content": "hello"}]
    assert graph.configs[0] == {
        "configurable": {
            "thread_id": "alice:conv-1",
            "checkpoint_ns": "seki-agent",
        }
    }


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


def test_default_runner_falls_back_when_langgraph_is_unavailable() -> None:
    runner = create_default_agent_runner(
        RagService(answerer=lambda question: {"answer": f"rag: {question}", "sources": []}),
        prefer_langgraph=True,
    )

    if all(importlib.util.find_spec(module) for module in ("langgraph", "langchain", "langchain_openai")):
        assert isinstance(runner, LangGraphAgentRunner)
    else:
        assert isinstance(runner.rag_tool, RagAgentTool)
