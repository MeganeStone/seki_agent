from app.services.agent_runner import AgentRequest, RuleBasedAgentRunner
from app.services.agent_tools import AgentToolResult


class FakeRagTool:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, question: str) -> AgentToolResult:
        self.calls.append(question)
        return AgentToolResult(content=f"rag: {question}", data={"sources": [{"file_name": "manual.pdf"}]})


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
