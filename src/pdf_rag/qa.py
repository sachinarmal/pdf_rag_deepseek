"""Retrieve relevant chunks and ask the LLM to answer from them."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage

from .config import Settings

# DeepSeek-R1 follows instructions best without a system prompt, so build_messages sends
# these instructions at the top of the user message instead.
SYSTEM_PROMPT = """You are a careful document assistant. Answer only from retrieved context.
If the answer is absent, say you cannot find it in the uploaded documents.
Do not invent facts. Cite sources inline as [filename, p. N].
Separate direct facts from interpretation."""

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_THINK_CLOSE_RE = re.compile(r"</think>", re.IGNORECASE)


def strip_think(text: str) -> str:
    """Remove DeepSeek-R1 <think>...</think> reasoning from a model answer."""
    text = _THINK_RE.sub("", text)
    # R1's chat template emits the opening <think> itself, so output can hold only "</think>".
    return _THINK_CLOSE_RE.split(text)[-1].strip()


def cite(doc: Document) -> str:
    return f"[{doc.metadata.get('source', '?')}, p. {doc.metadata.get('page', '?')}]"


def format_context(docs: list[Document]) -> str:
    return "\n\n".join(f"{cite(d)}\n{d.page_content}" for d in docs)


def build_messages(question: str, docs: list[Document]) -> list:
    return [
        HumanMessage(
            content=f"{SYSTEM_PROMPT}\n\nCONTEXT:\n{format_context(docs)}\n\nQUESTION: {question}"
        ),
    ]


@dataclass
class Answer:
    text: str
    sources: list[Document] = field(default_factory=list)


class RagPipeline:
    """Question answering over an existing Chroma index.

    `store` and `llm` can be injected (used by tests); otherwise they are
    built from settings.
    """

    def __init__(self, settings: Settings, store=None, llm=None):
        self.settings = settings
        if store is None:
            from .indexing import open_store
            store = open_store(settings)
        if llm is None:
            from langchain_ollama import ChatOllama
            llm = ChatOllama(
                model=settings.llm_model,
                base_url=settings.ollama_base_url,
                temperature=settings.llm_temperature,
                reasoning=settings.llm_reasoning,
                num_ctx=settings.llm_num_ctx,
            )
        self.store = store
        self.llm = llm

    def retrieve(self, question: str) -> list[Document]:
        return self.store.similarity_search(question, k=self.settings.top_k)

    def ask(self, question: str) -> Answer:
        docs = self.retrieve(question)
        if not docs:
            return Answer("The index is empty. Ingest and index some PDFs first.")
        response = self.llm.invoke(build_messages(question, docs))
        return Answer(strip_think(response.content), docs)
