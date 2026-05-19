import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path

from fastapi import HTTPException, status

from app.core.config import get_settings
from app.schemas.chat import ChatSource


RagAnswerer = Callable[[str], dict | str]


class RagService:
    def __init__(
        self,
        answerer: RagAnswerer | None = None,
        legacy_src_dir: Path | None = None,
    ):
        settings = get_settings()
        self.legacy_src_dir = legacy_src_dir or settings.legacy_src_dir
        self.answerer = answerer
        self._qa_chain = None

    def answer(
        self,
        message: str,
        use_knowledge_base: bool = True,
    ) -> dict:
        clean_message = message.strip()
        if not clean_message:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="message is required")

        if use_knowledge_base:
            return self._answer_with_rag(clean_message)
        return {"answer": "知识库已禁用，当前接口仅提供知识库问答。", "sources": []}

    def _answer_with_rag(self, question: str) -> dict:
        if self.answerer is not None:
            result = self.answerer(question)
            if isinstance(result, str):
                return {"answer": result, "sources": []}
            return {
                "answer": str(result.get("answer", "")),
                "sources": [self._source_from_dict(source) for source in result.get("sources", [])],
            }

        settings = get_settings()
        if not settings.rag_api_key:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="RAG API key is not configured")

        rag_module, vector_db_module = self._load_legacy_modules()
        if self._qa_chain is None:
            vector_db = vector_db_module.get_vector_db(settings.rag_api_key)
            self._qa_chain = rag_module.build_qa_chain(vector_db, settings.rag_api_key)

        answer = rag_module.rag_qa_chain(question, self._qa_chain)
        return {"answer": answer, "sources": []}

    def _load_legacy_modules(self):
        if str(self.legacy_src_dir) not in sys.path:
            sys.path.insert(0, str(self.legacy_src_dir))
        rag_module = self._load_module("legacy_rag", self.legacy_src_dir / "rag.py")
        vector_db_module = self._load_module("legacy_vector_db", self.legacy_src_dir / "vector_db.py")
        return rag_module, vector_db_module

    @staticmethod
    def _load_module(name: str, path: Path):
        if not path.exists():
            raise RuntimeError(f"Legacy module not found: {path}")
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Failed to load module: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @staticmethod
    def _source_from_dict(source: dict) -> ChatSource:
        return ChatSource(
            file_name=source.get("file_name"),
            page_number=source.get("page_number"),
            snippet=source.get("snippet"),
        )
