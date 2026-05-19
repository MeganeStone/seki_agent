from dataclasses import dataclass


@dataclass(frozen=True)
class WebSearchResult:
    summary: str
    items: list[dict]


class WebSearchDisabledError(RuntimeError):
    pass


class DisabledWebSearchService:
    def search(self, query: str, max_results: int = 5) -> WebSearchResult:
        raise WebSearchDisabledError("Web search is not configured")
