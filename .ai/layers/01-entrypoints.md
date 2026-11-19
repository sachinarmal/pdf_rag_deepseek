# Layer 1: Entrypoints

There are three ways execution enters the system. There are **no** HTTP routes, middleware, timers, signal handlers or jobs. Streamlit serves its own internal endpoints; the app defines none.

| Entry | How it's invoked | Defined in |
|---|---|---|
| `pdf-rag` console script | `pdf-rag <command>` | `pyproject.toml` `[project.scripts]` → `src/pdf_rag/cli.py` `main` |
| Module run | `python -m pdf_rag <command>` | `src/pdf_rag/__main__.py` → `cli.main` |
| Streamlit app | `streamlit run app/streamlit_app.py` | `app/streamlit_app.py` (runs as a script, top to bottom) |

## CLI: `src/pdf_rag/cli.py`

Boot order in `main(argv)`: build the `argparse` parser → `parse_args` → `logging.basicConfig` (INFO with `-v/--verbose`, else WARNING) → `args.func(args)`. `FileNotFoundError` and `ValueError` are caught and printed as `error: …` to stderr, with exit code `1`. Success returns `0`.

| Command | Handler | Calls | Needs Ollama |
|---|---|---|---|
| `ingest` | `cmd_ingest` | `ingest.ingest_dir(s.raw_dir, s.pages_file, s.ocr)`: **replaces** `pages.jsonl` | no |
| `index` | `cmd_index` | `indexing.rebuild_index(s)`: **drops and rebuilds** the collection | yes (embeddings) |
| `ask <question…>` | `cmd_ask` | `RagPipeline(get_settings()).ask(...)`, then `_print_answer` | yes |
| `chat` | `cmd_chat` | loops on `input()`; `exit`/`quit`/EOF/Ctrl-C returns `0` | yes |

- Handlers import their dependencies inside the function (`from .ingest import ingest_dir`, etc.), so `pdf-rag --help` doesn't load langchain or pdfplumber. Keep that pattern for new commands.
- To add a command: write a `cmd_<name>(args) -> int` and register it in `main` with `sub.add_parser(...).set_defaults(func=cmd_<name>)`.
- `[AS-IS REALITY]` `main` catches **all** `ValueError`s as user errors, so a programming bug that raises `ValueError` prints as a one-line `error:` with no traceback. It's there so a bad `OCR_MODE` or a non-integer env var gets a clean message.
- `[AS-IS REALITY]` `_print_answer` lists one line per retrieved chunk, so the same page can appear several times. The Streamlit app removes duplicates; the CLI doesn't.

## Streamlit: `app/streamlit_app.py`

Streamlit re-runs the whole script on every interaction. Order on each run:

1. `st.set_page_config`, then `settings = get_settings()` at module level.
2. `get_pipeline()` is decorated with `@st.cache_resource`, so **one `RagPipeline` per server process** is shared by all sessions. A failure shows `st.error` and calls `st.stop()`.
3. **Sidebar:** `st.file_uploader` (PDF, multiple). The "Index N PDF(s)" button:
   1. writes each upload to `settings.raw_dir / Path(f.name).name`, which strips path components (this is the path-traversal guard);
   2. calls `ingest_files(saved, settings.pages_file, settings.ocr)`, which merges into `pages.jsonl`;
   3. calls `upsert_records(pipeline.store, records, settings)`, which replaces those sources' chunks.

   Then it shows the `count_chunks` metric and a "Clear chat" button.
4. **Chat:** replays `st.session_state.messages`, then `st.chat_input` → `pipeline.ask` → render the answer and the deduplicated `cite(d)` list in a "Sources" expander → append to history.

- `[AS-IS REALITY]` `get_settings()` runs **outside** the `try`, so an invalid env value (for example `TOP_K=abc`) crashes the page with a traceback instead of `st.error`.
- `[AS-IS REALITY]` The UI reaches into `pipeline.store` (a `RagPipeline` attribute) to upsert and count. There's no indexing method on the pipeline.
- `[AS-IS REALITY]` Ingestion and OCR run synchronously inside the script run (about 3 s per OCR'd page), which blocks that session's UI. There's no app-level limit on upload size or page count.
- `[AS-IS REALITY]` Broad `except Exception` blocks show raw exception text in the UI (`Indexing failed: …`, `⚠️ Error: …`), and a failing `count_chunks` is silently swallowed.
- `[AS-IS REALITY]` An upload whose file name matches an existing file **silently overwrites** it in `data/raw/` and replaces its records and chunks, even if the content is different.
- UI styling: only Streamlit's defaults. There's no theme file (`.streamlit/` doesn't exist), no custom CSS and no icon library; the 📚 and ⚠️ emoji are used inline.

## Tests as entrypoints

`tests/` (pytest; `testpaths = ["tests"]` in `pyproject.toml`) call library functions directly with fakes. **Nothing tests `cli.py`, `indexing.py` or `app/streamlit_app.py`.**
