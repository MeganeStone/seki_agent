from app.services.web_search_service import VolcWebSearchService


class FakeResponse:
    encoding = "utf-8"

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def raise_for_status(self) -> None:
        return None

    def iter_lines(self, decode_unicode: bool = False):
        assert decode_unicode is True
        yield 'data: {"Result":{"Choices":[{"Delta":{"Content":"第一段"}}]}}'
        yield 'data: {"Result":{"Choices":[{"Delta":{"Content":"第二段"}}],"SearchResults":[{"Title":"标题","Url":"https://example.com","Snippet":"摘要"}]}}'
        yield "data: [DONE]"


def test_volc_web_search_service_parses_streaming_summary(monkeypatch) -> None:
    calls = []

    def fake_post(url, headers, json, stream, timeout):
        calls.append((url, headers, json, stream, timeout))
        return FakeResponse()

    monkeypatch.setattr("app.services.web_search_service.requests.post", fake_post)
    service = VolcWebSearchService(
        api_key="volc-key",
        api_url="https://search.example.test",
        timeout_seconds=7,
        max_summary_chars=100,
    )

    result = service.search("本田 最新新闻", max_results=3)

    assert result.summary == "第一段第二段"
    assert result.items == [
        {
            "title": "标题",
            "url": "https://example.com",
            "snippet": "摘要",
        }
    ]
    assert calls[0][0] == "https://search.example.test"
    assert calls[0][1]["Authorization"] == "Bearer volc-key"
    assert calls[0][2]["Query"] == "本田 最新新闻"
    assert calls[0][3] is True
    assert calls[0][4] == 7
