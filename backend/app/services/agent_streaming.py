"""Helpers for Agent SSE streaming and runner fallbacks."""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
from time import monotonic

from app.services.agent_runner import AgentRequest, AgentResponse, AgentStreamEvent


async def iter_runner_stream(request: AgentRequest, runner: object) -> AsyncIterator[AgentStreamEvent]:
    if hasattr(runner, "stream"):
        stream = runner.stream(request)
        if inspect.isasyncgen(stream):
            async for event in stream:
                yield event
            return
        for event in stream:
            yield event
        return

    result = runner.run(request)
    started = monotonic()
    for char in result.answer:
        yield AgentStreamEvent(kind="delta", text=char)
    yield AgentStreamEvent(
        kind="status",
        text=f"completed in {int((monotonic() - started) * 1000)}ms",
    )
    yield AgentStreamEvent(kind="final", response=result)


def stream_event_to_sse(event: AgentStreamEvent) -> str:
    import json

    payload: dict[str, object] = {}
    if event.kind == "delta":
        payload = {"text": event.text or ""}
    elif event.kind == "tool_start":
        payload = {
            "tool_name": event.tool_name or "tool",
            "tool_call_id": event.tool_call_id,
        }
    elif event.kind == "tool_end":
        payload = {
            "tool_name": event.tool_name or "tool",
            "tool_call_id": event.tool_call_id,
            "duration_ms": event.duration_ms,
            "preview": event.preview,
        }
    elif event.kind == "tool_error":
        payload = {
            "tool_name": event.tool_name or "tool",
            "tool_call_id": event.tool_call_id,
            "error": event.error or "tool failed",
            "duration_ms": event.duration_ms,
        }
    elif event.kind == "status":
        payload = {"text": event.text or ""}
    elif event.kind == "usage":
        payload = {
            "model_name": event.model_name or "model",
            "input_tokens": event.input_tokens or 0,
            "output_tokens": event.output_tokens or 0,
        }
    elif event.kind == "final" and event.response is not None:
        from app.schemas.chat import ChatMessageResponse
        from app.services.agent_runner import AgentResponse

        if isinstance(event.response, ChatMessageResponse):
            payload = event.response.model_dump(mode="json")
        elif isinstance(event.response, AgentResponse):
            payload = {
                "conversation_id": "",
                "answer": event.response.answer,
                "sources": event.response.sources,
                "route": event.response.route,
                "data": event.response.data,
            }
        else:
            payload = {"value": str(event.response)}

    data = json.dumps(payload, ensure_ascii=False)
    return f"event: {event.kind}\ndata: {data}\n\n"
