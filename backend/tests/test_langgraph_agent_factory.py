import sys
import types

from app.core.config import Settings
from app.services.agent_tools import FileLookupAgentTool, RagAgentTool, WebSearchAgentTool
from app.services.langgraph_agent_factory import create_tbox_langgraph_agent
from app.services.web_search_service import WebSearchResult


class FakeRagService:
    def answer(self, message: str, use_knowledge_base: bool = True) -> dict:
        return {"answer": message, "sources": []}


class FakeFileService:
    def list_files(self, owner_username: str) -> list:
        return []


class FakeWebSearchService:
    def search(self, query: str, max_results: int = 5) -> WebSearchResult:
        return WebSearchResult(summary=query, items=[])


def test_create_tbox_langgraph_agent_uses_injected_model_and_tools(monkeypatch) -> None:
    captured = {}

    def fake_create_agent(**kwargs):
        captured.update(kwargs)
        return {"graph": "ok"}

    fake_agents = types.ModuleType("langchain.agents")
    fake_agents.create_agent = fake_create_agent
    fake_langchain = types.ModuleType("langchain")
    fake_langchain.agents = fake_agents

    fake_openai = types.ModuleType("langchain_openai")
    fake_openai.ChatOpenAI = object

    fake_memory = types.ModuleType("langgraph.checkpoint.memory")
    fake_memory.InMemorySaver = lambda: "memory"

    monkeypatch.setitem(sys.modules, "langchain", fake_langchain)
    monkeypatch.setitem(sys.modules, "langchain.agents", fake_agents)
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_openai)
    monkeypatch.setitem(sys.modules, "langgraph.checkpoint.memory", fake_memory)

    graph = create_tbox_langgraph_agent(
        settings=Settings(rag_api_key="test-key"),
        rag_tool=RagAgentTool(FakeRagService()),
        web_search_tool=WebSearchAgentTool(FakeWebSearchService()),
        file_lookup_tool=FileLookupAgentTool(FakeFileService()),
        model_factory=lambda: "fake-model",
        checkpointer_factory=lambda: "fake-checkpointer",
    )

    assert graph == {"graph": "ok"}
    assert captured["model"] == "fake-model"
    assert captured["checkpointer"] == "fake-checkpointer"
    assert captured["system_prompt"]
    assert [tool.name for tool in captured["tools"]] == [
        "rag",
        "web_search",
        "file_lookup",
        "transfer_to_code_agent",
    ]


def test_create_tbox_langgraph_agent_can_disable_code_handoff_tool(monkeypatch) -> None:
    captured = {}

    def fake_create_agent(**kwargs):
        captured.update(kwargs)
        return {"graph": "ok"}

    fake_agents = types.ModuleType("langchain.agents")
    fake_agents.create_agent = fake_create_agent
    fake_langchain = types.ModuleType("langchain")
    fake_langchain.agents = fake_agents

    fake_openai = types.ModuleType("langchain_openai")
    fake_openai.ChatOpenAI = object

    fake_memory = types.ModuleType("langgraph.checkpoint.memory")
    fake_memory.InMemorySaver = lambda: "memory"

    monkeypatch.setitem(sys.modules, "langchain", fake_langchain)
    monkeypatch.setitem(sys.modules, "langchain.agents", fake_agents)
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_openai)
    monkeypatch.setitem(sys.modules, "langgraph.checkpoint.memory", fake_memory)

    create_tbox_langgraph_agent(
        settings=Settings(rag_api_key="test-key"),
        rag_tool=RagAgentTool(FakeRagService()),
        model_factory=lambda: "fake-model",
        checkpointer_factory=lambda: "fake-checkpointer",
        include_code_handoff_tool=False,
    )

    assert [tool.name for tool in captured["tools"]] == ["rag"]
