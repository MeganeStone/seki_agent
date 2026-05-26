from app.services.agent_runner import AgentRequest, AgentResponse
from app.services.multi_agent_graph_factory import create_multi_agent_graph


class FakeMainAgentGraph:
    def __init__(self, result: dict | None = None) -> None:
        self.states: list[dict] = []
        self.result = result or {"answer": "main answer", "route": "langgraph"}

    def invoke(self, state: dict) -> dict:
        self.states.append(state)
        return self.result


class RecordingCodeRunner:
    def __init__(self) -> None:
        self.requests: list[AgentRequest] = []

    def run(self, request: AgentRequest) -> AgentResponse:
        self.requests.append(request)
        return AgentResponse(answer=f"code: {request.message}", route="code_agent")


def test_multi_agent_graph_routes_default_state_to_main_agent() -> None:
    main_graph = FakeMainAgentGraph()
    graph = create_multi_agent_graph(
        main_graph,
        checkpointer_factory=lambda: None,
    )

    result = graph.invoke(
        {
            "owner_username": "alice",
            "conversation_id": "conv-1",
            "messages": [{"role": "user", "content": "hello"}],
        },
        config={"configurable": {"thread_id": "test-main"}},
    )

    assert main_graph.states[0]["owner_username"] == "alice"
    assert result["answer"] == "main answer"
    assert result["route"] == "langgraph"


def test_multi_agent_graph_routes_active_code_agent_to_code_runner() -> None:
    code_runner = RecordingCodeRunner()
    graph = create_multi_agent_graph(
        FakeMainAgentGraph(),
        code_agent_runner=code_runner,
        checkpointer_factory=lambda: None,
    )

    result = graph.invoke(
        {
            "owner_username": "alice",
            "conversation_id": "conv-1",
            "active_agent": "code_agent",
            "messages": [{"role": "user", "content": "继续调试脚本"}],
        },
        config={"configurable": {"thread_id": "test-code"}},
    )

    assert code_runner.requests == [
        AgentRequest(
            owner_username="alice",
            conversation_id="conv-1",
            message="继续调试脚本",
            agent_name="code_agent",
        )
    ]
    assert result["route"] == "code_agent"
    assert result["answer"] == "code: 继续调试脚本"
    assert result["active_agent"] == "code_agent"


def test_multi_agent_graph_honors_parent_command_handoff_to_code_agent() -> None:
    from langgraph.types import Command

    class HandoffMainGraph:
        def invoke(self, state: dict) -> Command:
            return Command(
                goto="code_agent",
                update={"active_agent": "code_agent"},
                graph=Command.PARENT,
            )

    code_runner = RecordingCodeRunner()
    graph = create_multi_agent_graph(
        HandoffMainGraph(),
        code_agent_runner=code_runner,
        checkpointer_factory=lambda: None,
    )

    result = graph.invoke(
        {
            "owner_username": "alice",
            "conversation_id": "conv-1",
            "messages": [{"role": "user", "content": "帮我写脚本"}],
        },
        config={"configurable": {"thread_id": "test-handoff"}},
    )

    assert code_runner.requests[0].agent_name == "code_agent"
    assert code_runner.requests[0].message == "帮我写脚本"
    assert result["route"] == "code_agent"


def test_multi_agent_graph_can_use_code_agent_graph() -> None:
    class FakeCodeAgentGraph:
        def __init__(self) -> None:
            self.states: list[dict] = []

        def invoke(self, state: dict) -> dict:
            self.states.append(state)
            return {"answer": "code graph answer", "route": "code_agent"}

    code_graph = FakeCodeAgentGraph()
    graph = create_multi_agent_graph(
        FakeMainAgentGraph(),
        code_agent_graph=code_graph,
        checkpointer_factory=lambda: None,
    )

    result = graph.invoke(
        {
            "owner_username": "alice",
            "conversation_id": "conv-1",
            "active_agent": "code_agent",
            "messages": [{"role": "user", "content": "列文件"}],
        },
        config={"configurable": {"thread_id": "test-code-graph"}},
    )

    assert code_graph.states[0]["owner_username"] == "alice"
    assert result["answer"] == "code graph answer"
    assert result["route"] == "code_agent"
    assert result["active_agent"] == "code_agent"


def test_multi_agent_graph_strips_main_history_when_route_initial_enters_code_agent() -> None:
    class FakeCodeAgentGraph:
        def __init__(self) -> None:
            self.states: list[dict] = []

        def invoke(self, state: dict) -> dict:
            self.states.append(state)
            return {"answer": "code graph answer", "route": "code_agent"}

    code_graph = FakeCodeAgentGraph()
    graph = create_multi_agent_graph(
        FakeMainAgentGraph(),
        code_agent_graph=code_graph,
        checkpointer_factory=lambda: None,
    )

    graph.invoke(
        {
            "owner_username": "alice",
            "conversation_id": "conv-1",
            "active_agent": "code_agent",
            "main_agent_messages": [
                {"role": "user", "content": "什么是 TSU"},
                {"role": "assistant", "content": "TSU 是..."},
            ],
            "code_agent_messages": [
                {"role": "user", "content": "创建脚本"},
                {"role": "assistant", "content": "脚本已创建"},
            ],
            "messages": [
                {"role": "user", "content": "什么是 TSU"},
                {"role": "assistant", "content": "TSU 是..."},
                {"role": "user", "content": "继续写脚本"},
            ],
        },
        config={"configurable": {"thread_id": "test-code-initial-clean-state"}},
    )

    assert code_graph.states[-1]["messages"] == [
        {"role": "user", "content": "创建脚本"},
        {"role": "assistant", "content": "脚本已创建"},
        {"role": "user", "content": "继续写脚本"},
    ]
    assert code_graph.states[-1]["agent_name"] == "code_agent"


def test_multi_agent_graph_honors_code_agent_transfer_to_main_command() -> None:
    from langgraph.types import Command

    class TransferBackCodeGraph:
        def invoke(self, state: dict) -> Command:
            return Command(
                goto="main_agent",
                update={"active_agent": "main_agent"},
                graph=Command.PARENT,
            )

    main_graph = FakeMainAgentGraph(result={"answer": "back to main", "route": "langgraph"})
    graph = create_multi_agent_graph(
        main_graph,
        code_agent_graph=TransferBackCodeGraph(),
        checkpointer_factory=lambda: None,
    )

    result = graph.invoke(
        {
            "owner_username": "alice",
            "conversation_id": "conv-1",
            "active_agent": "code_agent",
            "messages": [{"role": "user", "content": "什么是 TSU"}],
        },
        config={"configurable": {"thread_id": "test-transfer-back"}},
    )

    assert main_graph.states[-1]["active_agent"] == "main_agent"
    assert result["answer"] == "back to main"
    assert result["route"] == "langgraph"


def test_multi_agent_graph_strips_source_agent_messages_when_handing_back_to_main() -> None:
    from langgraph.types import Command

    class TransferBackCodeGraph:
        def invoke(self, state: dict) -> Command:
            return Command(
                goto="main_agent",
                update={"active_agent": "main_agent"},
                graph=Command.PARENT,
            )

    main_graph = FakeMainAgentGraph(result={"answer": "back to main", "route": "langgraph"})
    graph = create_multi_agent_graph(
        main_graph,
        code_agent_graph=TransferBackCodeGraph(),
        checkpointer_factory=lambda: None,
    )

    graph.invoke(
        {
            "owner_username": "alice",
            "conversation_id": "conv-1",
            "active_agent": "code_agent",
            "main_agent_messages": [
                {"role": "user", "content": "什么是 SIS"},
                {"role": "assistant", "content": "SIS 是..."},
            ],
            "code_agent_messages": [
                {"role": "user", "content": "写一个脚本"},
                {"role": "assistant", "content": "脚本已经写好"},
            ],
            "messages": [
                {"role": "user", "content": "写一个脚本"},
                {"role": "assistant", "content": "我来处理代码任务"},
                {"role": "tool", "content": "code_read_text_file: ok", "tool_call_id": "call-1"},
                {"role": "assistant", "content": "脚本已经写好"},
                {"role": "user", "content": "什么是 TSU"},
            ],
        },
        config={"configurable": {"thread_id": "test-transfer-back-clean-state"}},
    )

    assert main_graph.states[-1]["messages"] == [
        {"role": "user", "content": "什么是 SIS"},
        {"role": "assistant", "content": "SIS 是..."},
        {"role": "user", "content": "什么是 TSU"},
    ]
    assert main_graph.states[-1]["agent_name"] == "main_agent"


def test_multi_agent_graph_strips_source_agent_messages_when_handing_to_code_agent() -> None:
    from langgraph.types import Command

    class HandoffMainGraph:
        def invoke(self, state: dict) -> Command:
            return Command(
                goto="code_agent",
                update={"active_agent": "code_agent"},
                graph=Command.PARENT,
            )

    class FakeCodeAgentGraph:
        def __init__(self) -> None:
            self.states: list[dict] = []

        def invoke(self, state: dict) -> dict:
            self.states.append(state)
            return {"answer": "code graph answer", "route": "code_agent"}

    code_graph = FakeCodeAgentGraph()
    graph = create_multi_agent_graph(
        HandoffMainGraph(),
        code_agent_graph=code_graph,
        checkpointer_factory=lambda: None,
    )

    graph.invoke(
        {
            "owner_username": "alice",
            "conversation_id": "conv-1",
            "main_agent_messages": [
                {"role": "user", "content": "什么是 TSU"},
                {"role": "assistant", "content": "TSU 是..."},
            ],
            "code_agent_messages": [
                {"role": "user", "content": "创建脚本"},
                {"role": "assistant", "content": "脚本已创建"},
            ],
            "messages": [
                {"role": "user", "content": "什么是 TSU"},
                {"role": "assistant", "content": "TSU 是..."},
                {"role": "user", "content": "帮我写脚本"},
            ],
        },
        config={"configurable": {"thread_id": "test-handoff-clean-state"}},
    )

    assert code_graph.states[-1]["messages"] == [
        {"role": "user", "content": "创建脚本"},
        {"role": "assistant", "content": "脚本已创建"},
        {"role": "user", "content": "帮我写脚本"},
    ]
    assert code_graph.states[-1]["agent_name"] == "code_agent"
