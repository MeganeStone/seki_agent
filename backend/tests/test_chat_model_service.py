import pytest
from fastapi import HTTPException

from app.services.chat_model_service import ChatModelService


def test_chat_model_service_uses_injected_caller() -> None:
    service = ChatModelService(caller=lambda message, api_key: f"{message}:{api_key}")

    result = service.answer("hello", api_key="request-key")

    assert result == {"answer": "hello:request-key", "sources": []}


def test_chat_model_service_requires_api_key(monkeypatch) -> None:
    monkeypatch.setenv("SEKI_RAG_API_KEY", "")
    from app.core.config import get_settings

    get_settings.cache_clear()
    service = ChatModelService()

    with pytest.raises(HTTPException) as exc_info:
        service.answer("hello")

    assert exc_info.value.status_code == 503
    assert "Agent API key" in exc_info.value.detail
    get_settings.cache_clear()
