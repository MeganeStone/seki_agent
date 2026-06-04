from collections.abc import Callable

from fastapi import HTTPException, status

from app.core.config import get_settings
from app.services.agent_prompts import TBOX_AGENT_SYSTEM_PROMPT
from app.services.agent_runner import ChatHistoryMessage
from app.services.conversation_history import MAX_CONTEXT_MESSAGES, format_messages_for_summarization


ChatModelCaller = Callable[[str, str | None], str]


class ChatModelService:
    def __init__(self, caller: ChatModelCaller | None = None):
        self.caller = caller

    def answer(
        self,
        message: str,
        api_key: str | None = None,
        history: tuple[ChatHistoryMessage, ...] = (),
    ) -> dict:
        clean_message = message.strip()
        if not clean_message:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="message is required")

        if self.caller is not None:
            return {"answer": self.caller(clean_message, api_key), "sources": []}

        settings = get_settings()
        effective_api_key = settings.rag_api_key or api_key
        if not effective_api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="请先配置 Agent API key，或在前端输入临时 API key。",
            )

        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="普通聊天模型依赖未安装，请安装 langchain-openai。",
            ) from exc

        model = ChatOpenAI(
            model=settings.rag_model_name,
            temperature=0.2,
            api_key=effective_api_key,
            base_url=settings.rag_base_url,
            timeout=300,
        )
        messages = [{"role": "system", "content": TBOX_AGENT_SYSTEM_PROMPT}]
        for item in history[-MAX_CONTEXT_MESSAGES:]:
            if item.role in {"user", "assistant"} and item.content.strip():
                messages.append({"role": item.role, "content": item.content})
        messages.append({"role": "user", "content": clean_message})
        response = model.invoke(messages)
        return {"answer": _message_content(response), "sources": []}

    def summarize_messages(
        self,
        messages: tuple[ChatHistoryMessage, ...],
        previous_summary: str | None = None,
        api_key: str | None = None,
    ) -> str:
        transcript = format_messages_for_summarization(messages)
        if not transcript.strip() and previous_summary:
            return previous_summary
        if not transcript.strip():
            return "No earlier conversation content."

        if self.caller is not None:
            prompt = _summarize_prompt(transcript, previous_summary)
            return self.caller(prompt, api_key)

        settings = get_settings()
        effective_api_key = settings.rag_api_key or api_key
        if not effective_api_key:
            from app.services.conversation_history import _fallback_summarize

            return _fallback_summarize(messages, previous_summary)

        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            from app.services.conversation_history import _fallback_summarize

            return _fallback_summarize(messages, previous_summary)

        model = ChatOpenAI(
            model=settings.rag_model_name,
            temperature=0,
            api_key=effective_api_key,
            base_url=settings.rag_base_url,
            timeout=120,
        )
        response = model.invoke(
            [
                {
                    "role": "system",
                    "content": (
                        "You compress prior chat history into a concise Chinese summary for the model context. "
                        "Preserve user goals, decisions, file names, task ids, tool outcomes, and open questions. "
                        "Do not invent facts."
                    ),
                },
                {"role": "user", "content": _summarize_prompt(transcript, previous_summary)},
            ]
        )
        return _message_content(response).strip() or _fallback_summarize(messages, previous_summary)


def _summarize_prompt(transcript: str, previous_summary: str | None) -> str:
    if previous_summary:
        return (
            "Update the existing summary with the new messages below.\n\n"
            f"Existing summary:\n{previous_summary}\n\n"
            f"New messages:\n{transcript}"
        )
    return f"Summarize the conversation messages below:\n\n{transcript}"


def _fallback_summarize(
    messages: tuple[ChatHistoryMessage, ...],
    previous_summary: str | None,
) -> str:
    from app.services.conversation_history import _fallback_summarize as inner

    return inner(messages, previous_summary)


def _message_content(message: object) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                value = item.get("text") or item.get("content")
                if value:
                    parts.append(str(value))
            elif item is not None:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content or "")
