from app.services.agent_handoff_tools import create_transfer_to_code_agent_tool, create_transfer_to_main_agent_tool


def test_transfer_to_code_agent_tool_returns_langgraph_command() -> None:
    tool = create_transfer_to_code_agent_tool()

    result = tool.invoke({})

    assert tool.name == "transfer_to_code_agent"
    assert "code_agent" in tool.description
    assert result.goto == "code_agent"
    assert result.update == {"active_agent": "code_agent"}
    assert result.graph == "__parent__"


def test_transfer_to_code_agent_tool_can_customize_target_name() -> None:
    tool = create_transfer_to_code_agent_tool(code_agent_name="custom_code_agent")

    result = tool.invoke({})

    assert result.goto == "custom_code_agent"
    assert result.update == {"active_agent": "custom_code_agent"}


def test_transfer_to_main_agent_tool_returns_langgraph_command() -> None:
    tool = create_transfer_to_main_agent_tool()

    result = tool.invoke({})

    assert tool.name == "transfer_to_main_agent"
    assert "main_agent" in tool.description
    assert result.goto == "main_agent"
    assert result.update == {"active_agent": "main_agent"}
    assert result.graph == "__parent__"
