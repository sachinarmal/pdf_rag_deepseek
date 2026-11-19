"""Chunk page records and store their embeddings in ChromaDB."""

from __future__ import annotations

import logging
from collections.abc import Iterable

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .config import Settings
from .ingest import read_records

log = logging.getLogger(__name__)


def records_to_documents(records: Iterable[dict]) -> list[Document]:
    return [Document(page_content=r["text"], metadata=r["metadata"]) for r in records]


def chunk_documents(docs: list[Document], settings: Settings) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap
    )
    return splitter.split_documents(docs)


def open_store(settings: Settings) -> Chroma:
    embeddings = OllamaEmbeddings(model=settings.embed_model, base_url=settings.ollama_base_url)
    settings.chroma_dir.mkdir(parents=True, exist_ok=True)
    return Chroma(
        collection_name=settings.collection_name,
        embedding_function=embeddings,
        persist_directory=str(settings.chroma_dir),
    )


def count_chunks(store: Chroma) -> int:
    return len(store.get(include=[])["ids"])


def upsert_records(store: Chroma, records: list[dict], settings: Settings) -> int:
    """Replace any chunks from the same source files, then add the new ones."""
    sources = {r["metadata"]["source"] for r in records}
    for source in sources:
        ids = store.get(where={"source": source}, include=[])["ids"]
        if ids:
            store.delete(ids=ids)
    chunks = chunk_documents(records_to_documents(records), settings)
    if chunks:
        store.add_documents(chunks)
    return len(chunks)


def rebuild_index(settings: Settings) -> int:
    """Drop the collection and re-index everything in pages_file."""
    records = read_records(settings.pages_file)
    if not records:
        raise FileNotFoundError(
            f"{settings.pages_file} is missing or empty; run `pdf-rag ingest` first."
        )
    open_store(settings).delete_collection()
    store = open_store(settings)
    n = upsert_records(store, records, settings)
    log.info("Indexed %d chunks from %d pages", n, len(records))
    return n
