# .ai Context Changelog

All notable changes to the `.ai/` context documentation. Newest first.

<!-- New entries go directly below this line, in this format:
## [YYYY-MM-DD] - <Task Name>
- **Scope**: <Modified files / directories>
- **Summary**: <Brief functional summary of changes>
- **Doc Updates**: <Which .ai/ context files were updated, or "none">
-->

## [2026-11-19] - Fork as DeepSeek-R1 project
- **Scope**: whole project copied from `pdf_rag_qwen14_upgrade` to `pdf_rag_deepseek` (no `.git`, `.venv`, caches or index); `src/pdf_rag/config.py`, `src/pdf_rag/qa.py`, `src/pdf_rag/__init__.py`, `pyproject.toml`, `.env.example`, `README.md`, `CLAUDE.md`, `tests/test_config.py`, `tests/test_qa.py`
- **Summary**: Default chat model is now `deepseek-r1:14b` with temperature 0.6. New `LLM_NUM_CTX` setting (default 16384) is passed to `ChatOllama`. The prompt is sent as one user message, with no system message. `strip_think` also drops reasoning before a lone `</think>`. Embeddings are unchanged (`bge-m3`). This project needs a fresh `pdf-rag ingest` and `pdf-rag index`.
- **Doc Updates**: `00-INDEX.md`, `layers/02-domain-logic.md`, `CLAUDE.md`

## [0.1.0] - 2026-11-17 - Baseline snapshot
- **Scope**: `.ai/`, `CLAUDE.md` (documentation only; no code changes)
- **Summary**: First map of the code at commit `2affaa9`: the `pdf_rag` package (config, ingest with auto-OCR for garbled Devanagari, indexing, qa), the `pdf-rag` CLI, the Streamlit app, local `data/` storage and 19 pytest tests. Records the current `[AS-IS REALITY]` debt.
- **Doc Updates**: created `00-INDEX.md`, `layers/01-entrypoints.md`, `layers/02-domain-logic.md`, `layers/03-data-and-state.md`, `domains/.gitkeep`, and this changelog
