"""Runtime settings, read from environment variables (and a `.env` file if present)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _env_bool(name: str, default: bool) -> bool:
    return _env(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str
    llm_model: str
    llm_temperature: float
    llm_reasoning: bool
    llm_num_ctx: int
    embed_model: str
    data_dir: Path
    chroma_dir: Path
    collection_name: str
    ocr_lang: str
    ocr_mode: str
    ocr_dpi: int
    chunk_size: int
    chunk_overlap: int
    top_k: int

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def pages_file(self) -> Path:
        return self.data_dir / "processed" / "pages.jsonl"

    @property
    def ocr(self):
        from .ingest import OcrOptions
        return OcrOptions(lang=self.ocr_lang, mode=self.ocr_mode, dpi=self.ocr_dpi)

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(_env("DATA_DIR", "data"))
        return cls(
            ollama_base_url=_env("OLLAMA_BASE_URL", "http://localhost:11434"),
            llm_model=_env("LLM_MODEL", "deepseek-r1:14b"),
            # DeepSeek recommends 0.5-0.7 for R1; lower values tend to cause repetition.
            llm_temperature=float(_env("LLM_TEMPERATURE", "0.6")),
            llm_reasoning=_env_bool("LLM_REASONING", False),
            # Ollama's default window is too small for top-k Devanagari chunks + R1 output.
            llm_num_ctx=int(_env("LLM_NUM_CTX", "16384")),
            embed_model=_env("EMBED_MODEL", "bge-m3"),
            data_dir=data_dir,
            chroma_dir=Path(_env("CHROMA_DIR", str(data_dir / "chroma"))),
            collection_name=_env("COLLECTION_NAME", "pdf_rag"),
            ocr_lang=_env("OCR_LANG", "eng+mar"),
            ocr_mode=_env("OCR_MODE", "auto").strip().lower(),
            ocr_dpi=int(_env("OCR_DPI", "300")),
            chunk_size=int(_env("CHUNK_SIZE", "1000")),
            chunk_overlap=int(_env("CHUNK_OVERLAP", "150")),
            top_k=int(_env("TOP_K", "5")),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()
    return Settings.from_env()
