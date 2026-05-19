from collections.abc import Callable
from typing import Any

from app.services.agent_tools import (
    DiffAgentTool,
    FileLookupAgentTool,
    RagAgentTool,
    SpiAgentTool,
    TranslationAgentTool,
    WebSearchAgentTool,
)


class MissingLangChainToolDependencyError(RuntimeError):
    pass


def create_langchain_tools(
    rag_tool: RagAgentTool,
    web_search_tool: WebSearchAgentTool | None = None,
    file_lookup_tool: FileLookupAgentTool | None = None,
    translation_tool: TranslationAgentTool | None = None,
    spi_tool: SpiAgentTool | None = None,
    diff_tool: DiffAgentTool | None = None,
    owner_username: str | None = None,
) -> list[Any]:
    try:
        from langchain_core.tools import StructuredTool
    except ImportError as exc:
        raise MissingLangChainToolDependencyError("langchain-core is required to create LangChain tools") from exc

    tools = [
        StructuredTool.from_function(
            func=_rag_func(rag_tool),
            name="rag",
            description=(
                "回答公司业务、TSU/TBOX、项目文档相关问题。"
                "仅当用户询问公司业务或明确要求查知识库时使用。"
                "参数：question 为用户原始问题。"
            ),
        )
    ]

    if web_search_tool is not None:
        tools.append(
            StructuredTool.from_function(
                func=_web_search_func(web_search_tool),
                name="web_search",
                description=(
                    "联网搜索公开信息。仅当用户明确要求搜索互联网、查询最新信息、新闻、外部资料时使用。"
                    "不要用于公司内部知识库问题；内部业务问题优先使用 rag。"
                    "参数：query 搜索关键词，max_results 返回结果数量上限。"
                ),
            )
        )

    if file_lookup_tool is not None:
        tools.append(
            StructuredTool.from_function(
                func=_file_lookup_func(file_lookup_tool, owner_username),
                name="file_lookup",
                description=(
                    "查询当前用户已上传文件，返回可用于其他工具的 file_id。"
                    "当用户只提供文件名、文件后缀或自然语言描述，而没有提供 file_id 时，必须先使用此工具。"
                    "参数：filename_contains 文件名包含的关键词，suffix 文件后缀如 .docx/.log/.tar.gz，limit 返回数量上限。"
                ),
            )
        )

    if translation_tool is not None:
        tools.append(
            StructuredTool.from_function(
                func=_translation_func(translation_tool, owner_username),
                name="translation",
                description=(
                    "创建文档翻译任务。仅当用户明确要求翻译已上传文件时使用。"
                    "不要编造 file_id；file_id 必须来自用户已上传文件或前端选择。"
                    "参数：file_id 已上传文件 ID，target_language 目标语言。"
                ),
            )
        )

    if spi_tool is not None:
        tools.append(
            StructuredTool.from_function(
                func=_spi_func(spi_tool, owner_username),
                name="spi",
                description=(
                    "创建 SPI log 解析任务。仅当用户明确要求解析已上传 .log 文件时使用。"
                    "不要编造 file_id；file_id 必须来自用户已上传文件或前端选择。"
                    "参数：file_id 已上传 .log 文件 ID。"
                ),
            )
        )

    if diff_tool is not None:
        tools.append(
            StructuredTool.from_function(
                func=_diff_func(diff_tool, owner_username),
                name="diff",
                description=(
                    "创建版本差分任务。仅当用户明确要求比较两个已上传 .tar.gz 版本包时使用。"
                    "不要编造文件 ID；left_file_id 和 right_file_id 必须来自用户已上传文件或前端选择。"
                    "参数：left_file_id 旧版本文件 ID，right_file_id 新版本文件 ID。"
                ),
            )
        )

    return tools


def _web_search_func(tool: WebSearchAgentTool) -> Callable[[str, int], str]:
    def web_search(query: str, max_results: int = 5) -> str:
        """联网搜索公开信息。"""
        return tool(query, max_results).content

    return web_search


def _file_lookup_func(tool: FileLookupAgentTool, owner_username: str | None = None) -> Callable:
    if owner_username is not None:
        def file_lookup_bound(
            filename_contains: str | None = None,
            suffix: str | None = None,
            limit: int = 10,
        ) -> str:
            """查询当前用户已上传文件，返回文件 ID。"""
            return tool(owner_username, filename_contains, suffix, limit).content

        return file_lookup_bound

    def file_lookup(
        owner_username: str,
        filename_contains: str | None = None,
        suffix: str | None = None,
        limit: int = 10,
    ) -> str:
        """查询当前用户已上传文件，返回文件 ID。"""
        return tool(owner_username, filename_contains, suffix, limit).content

    return file_lookup


def _rag_func(tool: RagAgentTool) -> Callable[[str], str]:
    def rag(question: str) -> str:
        """回答公司业务、TSU/TBOX、项目文档相关问题。"""
        return tool(question).content

    return rag


def _translation_func(tool: TranslationAgentTool, owner_username: str | None = None) -> Callable:
    if owner_username is not None:
        def translation_bound(file_id: str, target_language: str) -> str:
            """创建文档翻译任务。"""
            return tool(owner_username, file_id, target_language).content

        return translation_bound

    def translation(owner_username: str, file_id: str, target_language: str) -> str:
        """创建文档翻译任务。"""
        return tool(owner_username, file_id, target_language).content

    return translation


def _spi_func(tool: SpiAgentTool, owner_username: str | None = None) -> Callable:
    if owner_username is not None:
        def spi_bound(file_id: str) -> str:
            """创建 SPI log 解析任务。"""
            return tool(owner_username, file_id).content

        return spi_bound

    def spi(owner_username: str, file_id: str) -> str:
        """创建 SPI log 解析任务。"""
        return tool(owner_username, file_id).content

    return spi


def _diff_func(tool: DiffAgentTool, owner_username: str | None = None) -> Callable:
    if owner_username is not None:
        def diff_bound(left_file_id: str, right_file_id: str) -> str:
            """创建版本差分任务。"""
            return tool(owner_username, left_file_id, right_file_id).content

        return diff_bound

    def diff(owner_username: str, left_file_id: str, right_file_id: str) -> str:
        """创建版本差分任务。"""
        return tool(owner_username, left_file_id, right_file_id).content

    return diff
