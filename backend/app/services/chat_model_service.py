from collections.abc import Callable

from fastapi import HTTPException, status

from app.core.config import get_settings


ChatModelCaller = Callable[[str, str | None], str]


class ChatModelService:
    def __init__(self, caller: ChatModelCaller | None = None):
        self.caller = caller

    def answer(self, message: str, api_key: str | None = None) -> dict:
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
        response = model.invoke(clean_message)
        return {"answer": _message_content(response), "sources": []}


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
