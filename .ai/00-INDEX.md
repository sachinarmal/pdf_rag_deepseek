# PDF RAG Assistant: Context Index

> Describes the code at commit `2affaa9` (2026-11-17). It records **what the code does today, not what it should do**. Items tagged `[AS-IS REALITY]` in the layer docs are known debt: don't copy them as patterns.

## 1. Application archetype

**Single-process local Python application**: an installable library (`src/pdf_rag/`) with two thin front ends, a CLI (`pdf-rag`) and a Streamlit web app (`app/streamlit_app.py`). There is no separate backend; the Streamlit app imports the library directly.

- **What it does:** retrieval-augmented question answering over the user's own PDFs. PDFs are turned into page text (pdfplumber, with Tesseract OCR for scanned pages or garbled Devanagari), split into chunks, embedded and stored in ChromaDB. Questions are answered by a local LLM using only the retrieved chunks, with `[filename, p. N]` citations.
- **Who uses it:** one person on their own machine (Mac or Linux), through the terminal or a browser at `localhost:8501`. The sample corpus is Marathi government documents (Maharashtra Vidhan Sabha question lists).
- **Integrations:** **Ollama** over HTTP (`OLLAMA_BASE_URL`) for the chat model and embeddings, and the **Tesseract** binary through `pytesseract`. Nothing else.
- **What it does NOT have:** no HTTP API or routes of its own, no authentication or users, no multi-tenancy, no SQL or ORM (Chroma's internal SQLite is the only database), no migrations, no background jobs, queues, cron or schedulers, no async code, no cloud services, API keys or secrets, no Docker, no CI/CD, no linter or formatter config, no frontend build (Streamlit renders the UI), and no notebooks.

## 2. Technology stack

| Concern | Choice (installed version in `.venv`) |
|---|---|
| Runtime | Python 3.12.7 (`requires-python >=3.10`) |
| Packaging | setuptools via `pyproject.toml`, src layout, console script `pdf-rag = pdf_rag.cli:main` |
| UI | Streamlit 1.67.0 |
| CLI | stdlib `argparse` |
| LLM / embeddings | Ollama 0.40.15 server; `langchain-ollama` 1.1.0 (`ChatOllama` → `deepseek-r1:14b`, `OllamaEmbeddings` → `bge-m3`) |
| Orchestration | `langchain-core` 1.7.6, `langchain-text-splitters` 1.1.3 (`RecursiveCharacterTextSplitter`) |
| Vector store | ChromaDB 1.5.9 via `langchain-chroma` 1.1.0, persisted on disk |
| PDF text / OCR | pdfplumber 0.11.10; pytesseract 0.3.13 → Tesseract 5.5.4 (`eng`, `mar` packs) |
| Config | `python-dotenv` 1.2.4 + env vars → frozen dataclass `Settings` |
| Persistence | Files under `data/` (JSONL + Chroma). See `layers/03-data-and-state.md` |
| Auth | None |
| Tests | pytest 9.2.0 (`[project.optional-dependencies] dev`), `tests/` |
| CI/CD | None |

**Environment variables:** none are required at boot. All are optional with defaults and are read once, on the first `get_settings()` call (`src/pdf_rag/config.py`). The full list with defaults is in `.env.example`: `OLLAMA_BASE_URL`, `LLM_MODEL`, `LLM_TEMPERATURE`, `LLM_REASONING`, `LLM_NUM_CTX`, `EMBED_MODEL`, `DATA_DIR`, `CHROMA_DIR`, `COLLECTION_NAME`, `OCR_LANG`, `OCR_MODE`, `OCR_DPI`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `TOP_K`.
**Needed at runtime:** a running Ollama server with both models pulled (for indexing and asking). Tesseract is optional; without it, OCR is skipped with a warning.

**Commands** (run from the repo root, venv active):

```bash
pip install -e ".[dev]"                 # install (editable) + pytest
python -m pytest -q                     # tests: no Ollama/Tesseract needed
pdf-rag ingest                          # data/raw/*.pdf → data/processed/pages.jsonl
pdf-rag index                           # pages.jsonl → data/chroma (full rebuild)
pdf-rag ask "question"  |  pdf-rag chat # Q&A (needs Ollama)
streamlit run app/streamlit_app.py      # web UI on :8501 (needs Ollama)
```

There is no build step and no lint command.

## 3. Folder map

★ entrypoint ◆ domain logic ▲ data and persistence

```
.
├── CLAUDE.md                 agent rules (read first)
├── .ai/                      this documentation
├── pyproject.toml            deps, console script, pytest config
├── requirements.txt          hand-maintained copy of the pyproject deps
├── .env.example              every env var with its default
├── app/
│   └── streamlit_app.py   ★  web UI: upload → ingest → upsert; chat
├── src/pdf_rag/
│   ├── __main__.py        ★  `python -m pdf_rag` → cli.main
│   ├── cli.py             ★  `pdf-rag` subcommands
│   ├── config.py             Settings / get_settings (env → dataclass)
│   ├── ingest.py          ◆▲ PDF → page records, OCR policy, pages.jsonl I/O
│   ├── indexing.py        ◆▲ chunking, Chroma open/upsert/rebuild
│   └── qa.py              ◆  retrieval, prompt, RagPipeline
├── tests/                    pytest, everything mocked
│   ├── test_config.py
│   ├── test_ingest.py
│   └── test_qa.py
└── data/                  ▲  all git-ignored except .gitkeep
    ├── raw/                  input PDFs
    ├── processed/            pages.jsonl
    └── chroma/               Chroma persistent store
```

## 4. Context lookup

| If your task is about… | Read |
|---|---|
| CLI commands, flags, exit codes, `python -m pdf_rag` | `layers/01-entrypoints.md` |
| Streamlit UI, upload flow, chat history, session state | `layers/01-entrypoints.md`, then `layers/03-data-and-state.md` (§ Frontend state) |
| Settings or env vars, adding a new setting | `layers/02-domain-logic.md` (§ config.py) |
| PDF extraction, OCR, tables, garbled Marathi text | `layers/02-domain-logic.md` (§ ingest.py) |
| Chunking, embeddings, re-indexing, duplicates | `layers/02-domain-logic.md` (§ indexing.py), then `layers/03-data-and-state.md` |
| Prompt, citations, retrieval, model output, `<think>` | `layers/02-domain-logic.md` (§ qa.py) |
| `pages.jsonl` or Chroma metadata shape, changing stored data | `layers/03-data-and-state.md` |
| Tests | `CLAUDE.md` § Prove It Works |
| Deep dive on a business area | `domains/` (empty: write one when a task first needs it) |
