import sys
import types
from pathlib import Path

from app.core.config import Settings
from app.services.code_agent_factory import CODE_AGENT_SYSTEM_PROMPT, create_code_langgraph_agent
from app.services.code_agent_tools import CodeAgentFileTool
from app.services.code_execution_service import CodeExecutionService
from app.services.code_operation_service import CodeOperationService


def test_create_code_langgraph_agent_uses_restricted_tools(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    def fake_create_agent(**kwargs):
        captured.update(kwargs)
        return {"graph": "code"}

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

    root = tmp_path / "project"
    root.mkdir()
    graph = create_code_langgraph_agent(
        settings=Settings(rag_api_key="test-key"),
        code_file_tool=CodeAgentFileTool(CodeExecutionService(allowed_roots=[root], default_root=root)),
        owner_username="alice",
        conversation_id="conv-1",
        model_factory=lambda: "fake-model",
        checkpointer_factory=lambda: "fake-checkpointer",
        operation_service=None,
    )

    assert graph == {"graph": "code"}
    assert captured["model"] == "fake-model"
    assert captured["checkpointer"] == "fake-checkpointer"
    assert captured["system_prompt"] == CODE_AGENT_SYSTEM_PROMPT
    assert [tool.name for tool in captured["tools"]] == [
        "code_list_dir",
        "code_create_dir",
        "code_read_text_file",
        "code_write_text_file",
        "code_run_python_script",
        "code_run_allowed_command",
        "code_delete_path",
        "transfer_to_main_agent",
    ]


def test_create_code_langgraph_agent_passes_operation_service(monkeypatch, tmp_path: Path, pg_dsn: str) -> None:
    captured = {}

    def fake_create_agent(**kwargs):
        captured.update(kwargs)
        return {"graph": "code"}

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

    root = tmp_path / "project"
    root.mkdir()
    from app.db.postgres import connect

    conn = connect(pg_dsn)
    operation_service = CodeOperationService(conn)
    graph = create_code_langgraph_agent(
        settings=Settings(rag_api_key="test-key"),
        code_file_tool=CodeAgentFileTool(CodeExecutionService(allowed_roots=[root], default_root=root)),
        owner_username="alice",
        conversation_id="conv-1",
        model_factory=lambda: "fake-model",
        checkpointer_factory=lambda: "fake-checkpointer",
        operation_service=operation_service,
    )

    assert graph == {"graph": "code"}
    assert [tool.name for tool in captured["tools"]][:2] == ["code_list_dir", "code_create_dir"]
    conn.close()
