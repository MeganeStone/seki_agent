from app.services.agent_runner_factory import _create_web_search_service
from app.services.web_search_service import DisabledWebSearchService, VolcWebSearchService


class SearchSettings:
    def __init__(self, web_search_api_key: str | None = None) -> None:
        self.web_search_api_key = web_search_api_key
        self.web_search_api_url = "https://example.test/search"
        self.web_search_timeout_seconds = 12.0
        self.web_search_max_summary_chars = 1234


def test_create_web_search_service_uses_env_configured_key() -> None:
    settings = SearchSettings(web_search_api_key="env-key")

    service = _create_web_search_service(settings)

    assert isinstance(service, VolcWebSearchService)
    assert service.api_key == "env-key"
    assert service.api_url == "https://example.test/search"
    assert service.timeout_seconds == 12.0
    assert service.max_summary_chars == 1234


def test_create_web_search_service_falls_back_to_disabled_without_key() -> None:
    settings = SearchSettings()

    service = _create_web_search_service(settings)

    assert isinstance(service, DisabledWebSearchService)
