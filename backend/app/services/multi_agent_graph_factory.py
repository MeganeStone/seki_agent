from typing import Literal, NotRequired

from typing_extensions import TypedDict

from app.services.agent_runner import AgentResponse


class MultiAgentState(TypedDict):
    messages: list
    active_agent: NotRequired[str]
    owner_username: NotRequired[str]
    conversation_id: NotRequired[str]
    agent_name: NotRequired[str]
    system_prompt: NotRequired[str]
    use_knowledge_base: NotRequired[bool]
    answer: NotRequired[str]
    route: NotRequired[str]
    data: NotRequired[dict]
    sources: NotRequired[list]


def create_multi_agent_graph(
    main_agent_graph,
    code_agent_graph=None,
    code_agent_runner=None,
    main_agent_name: str = "main_agent",
    code_agent_name: str = "code_agent",
    checkpointer_factory=None,
):
    """Compose the main LangGraph agent with an isolated code-agent placeholder."""

    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.errors import ParentCommand
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Command

    if checkpointer_factory is None:
        checkpointer_factory = InMemorySaver
    if code_agent_runner is None:
        from app.services.agent_runner import CodeAgentUnavailableRunner

        code_agent_runner = CodeAgentUnavailableRunner()

    def call_main_agent(state: MultiAgentState):
        try:
            result = main_agent_graph.invoke(dict(state))
        except ParentCommand as exc:
            command = exc.args[0]
            return Command(
                goto=command.goto,
                update=command.update,
            )
        if isinstance(result, Command) and result.graph == Command.PARENT:
            return Command(
                goto=result.goto,
                update=result.update,
            )
        return result

    def call_code_agent(state: MultiAgentState):
        if code_agent_graph is not None:
            try:
                result = code_agent_graph.invoke(dict(state))
            except ParentCommand as exc:
                command = exc.args[0]
                return Command(
                    goto=command.goto,
                    update=command.update,
                )
            if isinstance(result, Command) and result.graph == Command.PARENT:
                return Command(
                    goto=result.goto,
                    update=result.update,
                )
            if isinstance(result, dict):
                result = dict(result)
                result.setdefault("agent_name", code_agent_name)
                result.setdefault("active_agent", code_agent_name)
            return result

        messages = state.get("messages", [])
        last_message = messages[-1] if messages else {}
        content = _message_content(last_message)
        response = code_agent_runner.run(
            _request_from_state(
                state,
                message=content,
                agent_name=code_agent_name,
            )
        )
        return _response_to_state(response, code_agent_name)

    def route_initial(state: MultiAgentState) -> Literal["main_agent", "code_agent"]:
        return code_agent_name if state.get("active_agent") == code_agent_name else main_agent_name

    builder = StateGraph(MultiAgentState)
    builder.add_node(main_agent_name, call_main_agent, destinations=(code_agent_name, END))
    builder.add_node(code_agent_name, call_code_agent)
    builder.add_conditional_edges(START, route_initial, [main_agent_name, code_agent_name])
    builder.add_edge(main_agent_name, END)
    builder.add_edge(code_agent_name, END)
    return builder.compile(checkpointer=checkpointer_factory())


def _request_from_state(state: MultiAgentState, message: str, agent_name: str):
    from app.services.agent_runner import AgentRequest

    return AgentRequest(
        owner_username=str(state.get("owner_username") or ""),
        conversation_id=str(state.get("conversation_id") or ""),
        message=message,
        use_knowledge_base=bool(state.get("use_knowledge_base", True)),
        agent_name=agent_name,
    )


def _response_to_state(response: AgentResponse, agent_name: str) -> dict:
    return {
        "answer": response.answer,
        "sources": response.sources,
        "data": response.data,
        "route": response.route,
        "agent_name": agent_name,
        "active_agent": agent_name,
        "messages": [{"role": "assistant", "content": response.answer}],
    }


def _message_content(message: object) -> str:
    if isinstance(message, dict):
        return str(message.get("content") or "")
    return str(getattr(message, "content", "") or "")
