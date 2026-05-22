from app.services.agent_runner import AgentRequest, AgentResponse, HandoffAgentRunner, RuleBasedAgentRunner
from app.services.agent_tools import AgentToolResult


class FakeRagTool:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, question: str) -> AgentToolResult:
        self.calls.append(question)
        return AgentToolResult(content=f"rag: {question}", data={"sources": [{"file_name": "manual.pdf"}]})


class FakeChatTool:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def __call__(self, message: str, api_key: str | None = None) -> AgentToolResult:
        self.calls.append((message, api_key))
        return AgentToolResult(content=f"chat: {message}", data={"sources": []})


class FakeTranslationTool:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def __call__(self, owner_username: str, file_id: str, target_language: str) -> AgentToolResult:
        self.calls.append((owner_username, file_id, target_language))
        return AgentToolResult(content="translation created", data={"task_id": "translation-task"})


class FakeSpiTool:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __call__(self, owner_username: str, file_id: str) -> AgentToolResult:
        self.calls.append((owner_username, file_id))
        return AgentToolResult(content="spi created", data={"task_id": "spi-task"})


class FakeDiffTool:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def __call__(self, owner_username: str, left_file_id: str, right_file_id: str) -> AgentToolResult:
        self.calls.append((owner_username, left_file_id, right_file_id))
        return AgentToolResult(content="diff created", data={"task_id": "diff-task"})


class RecordingRunner:
    def __init__(self, route: str) -> None:
        self.route = route
        self.requests: list[AgentRequest] = []

    def run(self, request: AgentRequest) -> AgentResponse:
        self.requests.append(request)
        return AgentResponse(answer=f"{self.route}: {request.message}", route=self.route)


def request(message: str, use_knowledge_base: bool = True) -> AgentRequest:
    return AgentRequest(
        owner_username="alice",
        conversation_id="conv-1",
        message=message,
        use_knowledge_base=use_knowledge_base,
    )


def test_rule_runner_routes_default_messages_to_rag() -> None:
    rag_tool = FakeRagTool()
    runner = RuleBasedAgentRunner(rag_tool=rag_tool)

    response = runner.run(request("什么是 TSU？"))

    assert response.route == "rag"
    assert response.answer == "rag: 什么是 TSU？"
    assert response.sources == [{"file_name": "manual.pdf"}]
    assert rag_tool.calls == ["什么是 TSU？"]


def test_rule_runner_routes_translation_when_file_and_language_are_explicit() -> None:
    translation_tool = FakeTranslationTool()
    runner = RuleBasedAgentRunner(rag_tool=FakeRagTool(), translation_tool=translation_tool)

    response = runner.run(request("请翻译 file_id=file-1 target_language=英语"))

    assert response.route == "translation"
    assert response.data == {"task_id": "translation-task"}
    assert translation_tool.calls == [("alice", "file-1", "英语")]


def test_rule_runner_routes_spi_when_file_is_explicit() -> None:
    spi_tool = FakeSpiTool()
    runner = RuleBasedAgentRunner(rag_tool=FakeRagTool(), spi_tool=spi_tool)

    response = runner.run(request("解析 SPI file_id=log-1"))

    assert response.route == "spi"
    assert spi_tool.calls == [("alice", "log-1")]


def test_rule_runner_routes_diff_when_both_files_are_explicit() -> None:
    diff_tool = FakeDiffTool()
    runner = RuleBasedAgentRunner(rag_tool=FakeRagTool(), diff_tool=diff_tool)

    response = runner.run(request("比较版本 left_file_id=old-1 right_file_id=new-1"))

    assert response.route == "diff"
    assert diff_tool.calls == [("alice", "old-1", "new-1")]


def test_rule_runner_returns_direct_message_when_knowledge_base_disabled() -> None:
    runner = RuleBasedAgentRunner(rag_tool=FakeRagTool())

    response = runner.run(request("hello", use_knowledge_base=False))

    assert response.route == "direct"
    assert "未配置普通聊天模型" in response.answer


def test_rule_runner_uses_chat_tool_when_knowledge_base_disabled() -> None:
    chat_tool = FakeChatTool()
    runner = RuleBasedAgentRunner(rag_tool=FakeRagTool(), chat_tool=chat_tool)

    response = runner.run(
        AgentRequest(
            owner_username="alice",
            conversation_id="conv-1",
            message="hello",
            use_knowledge_base=False,
            api_key="request-key",
        )
    )

    assert response.route == "direct"
    assert response.answer == "chat: hello"
    assert chat_tool.calls == [("hello", "request-key")]


def test_handoff_runner_routes_code_tasks_to_isolated_code_agent() -> None:
    main_runner = RecordingRunner("main")
    code_runner = RecordingRunner("code_agent")
    runner = HandoffAgentRunner(main_runner=main_runner, code_runner=code_runner, enable_keyword_routing=True)

    response = runner.run(request("帮我写一个 Python 脚本处理日志"))

    assert response.route == "code_agent"
    assert main_runner.requests == []
    assert code_runner.requests == [
        AgentRequest(
            owner_username="alice",
            conversation_id="conv-1",
            message="帮我写一个 Python 脚本处理日志",
            use_knowledge_base=True,
            agent_name="code_agent",
            api_key=None,
        )
    ]


def test_handoff_runner_keyword_routing_stays_opt_in() -> None:
    main_runner = RecordingRunner("main")
    code_runner = RecordingRunner("code_agent")
    runner = HandoffAgentRunner(main_runner=main_runner, code_runner=code_runner)

    response = runner.run(request("帮我写一个 Python 脚本"))

    assert response.route == "main"
    assert code_runner.requests == []


def test_handoff_runner_does_not_guess_code_tasks_by_default() -> None:
    main_runner = RecordingRunner("main")
    code_runner = RecordingRunner("code_agent")
    runner = HandoffAgentRunner(main_runner=main_runner, code_runner=code_runner)

    response = runner.run(request("帮我写一个 Python 脚本处理日志"))

    assert response.route == "main"
    assert code_runner.requests == []
    assert main_runner.requests[0].agent_name == "main_agent"


def test_handoff_runner_routes_regular_tasks_to_main_agent() -> None:
    main_runner = RecordingRunner("main")
    code_runner = RecordingRunner("code_agent")
    runner = HandoffAgentRunner(main_runner=main_runner, code_runner=code_runner)

    response = runner.run(request("什么是 TSU？"))

    assert response.route == "main"
    assert code_runner.requests == []
    assert main_runner.requests[0].agent_name == "main_agent"


def test_handoff_runner_honors_existing_code_agent_context() -> None:
    main_runner = RecordingRunner("main")
    code_runner = RecordingRunner("code_agent")
    runner = HandoffAgentRunner(main_runner=main_runner, code_runner=code_runner)

    response = runner.run(
        AgentRequest(
            owner_username="alice",
            conversation_id="conv-1",
            message="继续",
            agent_name="code_agent",
        )
    )

    assert response.route == "code_agent"
    assert code_runner.requests[0].agent_name == "code_agent"


def test_agent_request_can_carry_user_api_key_without_changing_default_fields() -> None:
    req = request("hello")

    assert req.api_key is None

    req_with_key = AgentRequest(
        owner_username="alice",
        conversation_id="conv-1",
        message="hello",
        api_key="user-key",
    )

    assert req_with_key.agent_name == "main_agent"
    assert req_with_key.api_key == "user-key"
