# CLAUDE.md

Local PDF question-answering app: the `src/pdf_rag/` library, the `pdf-rag` CLI and a Streamlit UI, using Ollama (`deepseek-r1:14b`, `bge-m3`), ChromaDB and Tesseract. The code map is in `.ai/`.

## MANDATORY WORKFLOW

**Step 1: Pre-task context load** (before inspecting source code)
1. Read `.ai/00-INDEX.md`.
2. Read the 3 newest entries in `.ai/CHANGELOG.md`.
3. Use the index's lookup table to load **only** the `.ai/layers/` or `.ai/domains/` doc the task needs.

**Step 2: Code modification**
- Check *Reuse Before You Write* below before writing a new helper.
- If a change touches more than one file, first list the files you'll touch and the helpers you'll reuse.
- Stay in scope and keep the existing boundaries (see *Follow the Architecture*).

**Step 3: Documentation and changelog sync** (only if code, config or tests changed)
- If commands, settings or env vars, stored data shape, dependencies or public functions changed, update the matching `.ai/layers/*.md` (and `00-INDEX.md` if the stack, commands or folder map changed).
- If a business area needed deeper explanation than the layer docs give, create `.ai/domains/<area>.md` and add it to the index lookup table.
- Add an entry at the **top** of `.ai/CHANGELOG.md`:
  ```
  ## [YYYY-MM-DD] - <Task Name>
  - **Scope**: <Modified files / directories>
  - **Summary**: <Brief functional summary of changes>
  - **Doc Updates**: <Which .ai/ context files were updated, or "none">
  ```

## Reuse Before You Write

- **Settings:** `config.get_settings()` (cached) and `Settings` (`raw_dir`, `pages_file`, `ocr`). Never read `os.environ` or hardcode `data/...` paths anywhere else.
- **Text and OCR:** `ingest.clean`, `ingest.looks_garbled`, `ingest.resolve_ocr_lang`, `ingest.extract_page` / `extract_pdf`, `ingest.OcrOptions`.
- **Page-record I/O:** `ingest.read_records` / `write_records`. Merge by source with `ingest_files`; do a full replace with `ingest_dir`.
- **Vector store:** `indexing.open_store` is the only place a `Chroma` is built. Use `upsert_records` (it removes duplicates by `source`), `rebuild_index` and `count_chunks`.
- **Q&A:** `qa.RagPipeline` (`retrieve`, `ask`), `qa.cite` (the single citation formatter), `qa.strip_think`, `qa.build_messages`.
- **Test fakes:** `make_settings`, `FakeStore` and `FakeLLM` in `tests/test_qa.py`; `FakePage`, the `fake_ocr` fixture and the `GARBLED` / `CORRECT` Marathi samples in `tests/test_ingest.py`.
- **Known duplicates (don't add another copy):** removing duplicate sources is done in `app/streamlit_app.py` (`dict.fromkeys(cite(...))`) but not in `cli._print_answer`; replace-by-source exists in both `ingest_files` and `upsert_records`.

## Follow the Architecture

- Layering: `cli.py` / `app/streamlit_app.py` → `qa` / `indexing` / `ingest` → `config`. Front ends only wire calls together; put logic in `src/pdf_rag/`. Don't import `streamlit` from the package.
- New CLI command: a `cmd_<name>(args) -> int` in `cli.py` with lazy imports inside it, registered in `main`. New UI behaviour goes in `app/streamlit_app.py` and calls package functions.
- External clients (Ollama, Chroma, Tesseract) must stay injectable or easy to mock, the way `RagPipeline(settings, store=, llm=)` is.
- `ingest.py` (about 185 lines: extraction, OCR policy and JSONL I/O) is the largest module. Propose a split rather than adding another big concern to it.
- **These must change together:**
  - dependencies in `pyproject.toml` and `requirements.txt`;
  - the version in `pyproject.toml` and `src/pdf_rag/__init__.py`;
  - a new setting in the `Settings` field, `Settings.from_env`, `.env.example`, the README configuration table and `tests/test_qa.py` `make_settings`;
  - the citation format in `qa.SYSTEM_PROMPT` and `qa.cite`;
  - the CLI path (`ingest_dir` + `rebuild_index`) and the UI path (`ingest_files` + `upsert_records`).
- **Ask before** adding a library, a data store, a build or lint tool, or a new model provider.

## Keep Saved Data and Contracts Working

- `pages.jsonl` records (`text`, `metadata.source/page/method`) and Chroma chunk metadata are a contract: `upsert_records` filters on `source`, and `cite` and `_print_answer` read `source` and `page`. Don't rename or remove these keys. New keys must be optional, and readers must use `.get()` with defaults.
- There are no migrations or schema versions (see `.ai/layers/03-data-and-state.md`). If a change makes existing data stale (extraction or OCR logic, `EMBED_MODEL`, chunking), say so and give the regenerate command (`pdf-rag ingest`, then `pdf-rag index`).
- Env var names and defaults are a user-facing contract: don't rename them silently.
- There is no HTTP API. The CLI convention: user errors raise `FileNotFoundError` or `ValueError` and print `error: <msg>` to stderr with exit code `1`; success exits `0`. In the UI, failures show `st.error(...)`.

## Prove It Works

- pytest; tests go in `tests/test_<module>.py` as plain functions using `monkeypatch` and fakes. No test needs Ollama or Tesseract, and none are skipped.
- Run from the repo root with `.venv` active:
  - `python -m pytest -q`: must pass (21 tests at baseline).
  - `python -m compileall -q src app tests`: syntax check. There is no linter or formatter configured.
  - `pdf-rag --help`: checks the CLI still wires up.
- If you changed ingest, indexing or qa, also run it for real against a scratch copy of the data (needs Ollama): `DATA_DIR=/tmp/pdfrag-check pdf-rag ingest && DATA_DIR=/tmp/pdfrag-check pdf-rag index && DATA_DIR=/tmp/pdfrag-check pdf-rag ask "…"` after copying a PDF into `/tmp/pdfrag-check/raw/`.
- If you changed the UI: `streamlit run app/streamlit_app.py`, or headless via `streamlit.testing.v1.AppTest.from_file("app/streamlit_app.py")`.
- Before saying "done", report the commands you ran and their results. Say plainly what you couldn't run (for example, Ollama not running).
- `[AS-IS REALITY]` `indexing.py`, `cli.py` and the Streamlit app have no tests. Add tests when you change them.

## Scope and Style

- Do only what was asked. Mention unrelated debt (see the `[AS-IS REALITY]` tags in `.ai/layers/`) instead of fixing it.
- Python style: 4-space indent, double quotes, a module docstring on every module, `from __future__ import annotations` in package modules, type hints on public functions, `pathlib.Path` for paths, and dataclasses for value objects.
- Logging: `log = logging.getLogger(__name__)` with `%`-style arguments (`log.info("Reading %s", name)`). `print` only in `cli.py`. Use f-strings elsewhere.
- Heavy imports (langchain, pdfplumber) go inside functions in `cli.py`, and for default clients in `qa.RagPipeline`.
- Comments are short and explain *why*. Lines are about 100 characters or less.

## Safety

- Users' PDFs can be private. Never log or print document text. Logs carry only file names, page numbers and counts. Never commit anything under `data/` or put document content in external requests.
- Use file names from uploads or the user only after `Path(name).name`, as `app/streamlit_app.py` does, to block path traversal. Validate new user inputs (types, sizes, allowed values) the way `OcrOptions.__post_init__` validates the mode.
- There are no secrets today. If one is ever needed, read it through `Settings` from an env var, add it to `.env.example` with an empty value, and never hardcode it (`.env` is git-ignored).

## Styling (Streamlit UI)

- Streamlit defaults only: there's no `.streamlit/config.toml` theme, no custom CSS, and no icon library. Use built-in elements (`st.sidebar`, `st.chat_message`, `st.expander`, `st.metric`, `st.spinner`, `st.success` / `st.error`).
- Don't add `unsafe_allow_html`, raw hex colours or custom CSS without asking.

## Environment

- Python 3.12 venv at `.venv`. Install with `pip install -e ".[dev]"`. Run everything **from the repo root**: `DATA_DIR` and `.env` resolve against the CWD.
- Runtime needs Ollama running with `deepseek-r1:14b` and `bge-m3`. Tesseract with the `mar` pack is needed to OCR Marathi.
- To keep your work away from the user's real index, point `DATA_DIR` (and optionally `COLLECTION_NAME`) at a scratch folder. Don't run `pdf-rag ingest` or `pdf-rag index` against `data/` unless you were asked to, because they overwrite it.
- Speeds measured on this Mac: OCR about 3 s per page, `qwen3:14b` about 50 s per answer in the original Qwen project; `deepseek-r1:14b` about 85 s per answer (it always reasons first).
