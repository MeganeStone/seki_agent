from dataclasses import dataclass
import json

import requests


@dataclass(frozen=True)
class WebSearchResult:
    summary: str
    items: list[dict]


class WebSearchDisabledError(RuntimeError):
    pass


class DisabledWebSearchService:
    """未配置搜索 key 时使用的占位实现。"""

    def search(self, query: str, max_results: int = 5) -> WebSearchResult:
        raise WebSearchDisabledError("Web search is not configured")


class VolcWebSearchService:
    """火山/Feedcoop 兼容联网搜索封装。

    Agent 工具只关心 query -> 摘要结果；API key 可以来自后端环境变量，也可以
    来自前端本次请求的临时 key。临时 key 不落库，降低泄露面。
    """

    def __init__(
        self,
        api_key: str,
        api_url: str,
        timeout_seconds: float = 30.0,
        max_summary_chars: int = 4000,
    ):
        self.api_key = api_key
        self.api_url = api_url
        self.timeout_seconds = timeout_seconds
        self.max_summary_chars = max_summary_chars

    def search(self, query: str, max_results: int = 5) -> WebSearchResult:
        clean_query = query.strip()
        if not clean_query:
            return WebSearchResult(summary="请提供要搜索的关键词。", items=[])

        payload = {
            "Query": clean_query[:100],
            "SearchType": "web_summary",
            "Count": max(1, min(max_results, 10)),
            "NeedSummary": True,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            with requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                stream=True,
                timeout=self.timeout_seconds,
            ) as response:
                response.encoding = "utf-8"
                response.raise_for_status()
                summary_parts: list[str] = []
                items: list[dict] = []

                for raw_line in response.iter_lines(decode_unicode=True):
                    if not raw_line:
                        continue
                    line = raw_line.strip()
                    if line.startswith("data:"):
                        data_text = line[5:].strip()
                        if data_text == "[DONE]":
                            break
                        chunk = _load_json(data_text)
                        if chunk is None:
                            continue
                        _collect_volc_chunk(chunk, summary_parts, items)
                    else:
                        chunk = _load_json(line)
                        if chunk is not None:
                            _collect_volc_chunk(chunk, summary_parts, items)

                summary = "".join(summary_parts).strip()
                if not summary:
                    summary = "未获取到有效搜索总结。"
                return WebSearchResult(summary=summary[: self.max_summary_chars], items=items[: max_results])
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            return WebSearchResult(summary=f"联网搜索失败：HTTP {status}", items=[])
        except requests.RequestException as exc:
            return WebSearchResult(summary=f"联网搜索失败：{exc}", items=[])


def _load_json(value: str) -> dict | None:
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _collect_volc_chunk(chunk: dict, summary_parts: list[str], items: list[dict]) -> None:
    result = chunk.get("Result")
    if isinstance(result, dict):
        choices = result.get("Choices")
        if isinstance(choices, list):
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                delta = choice.get("Delta")
                if isinstance(delta, dict) and isinstance(delta.get("Content"), str):
                    summary_parts.append(delta["Content"])

        search_results = result.get("SearchResults") or result.get("SearchResult") or result.get("Items")
        if isinstance(search_results, list):
            for item in search_results:
                if isinstance(item, dict):
                    items.append(
                        {
                            "title": item.get("Title") or item.get("title"),
                            "url": item.get("Url") or item.get("URL") or item.get("url"),
                            "snippet": item.get("Snippet") or item.get("snippet") or item.get("Summary"),
                        }
                    )
