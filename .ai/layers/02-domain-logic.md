# Layer 2: Domain logic

All business rules live in `src/pdf_rag/`. The front ends (`cli.py`, `app/streamlit_app.py`) only wire calls together.

Dependency direction: `cli` / `app` → `qa`, `indexing`, `ingest` → `config`. Also `indexing` → `ingest` (for `read_records`), and `qa` → `indexing` (lazily, for `open_store`).

- `[AS-IS REALITY]` `config.Settings.ocr` imports `ingest.OcrOptions` lazily, so `config` depends on `ingest` (an inverted edge, imported inside the property to avoid a cycle). `OcrOptions` lives in `ingest.py`, not `config.py`.

## config.py: settings

- `Settings` is a frozen dataclass holding every tunable. Derived properties: `raw_dir` (`data_dir/raw`), `pages_file` (`data_dir/processed/pages.jsonl`) and `ocr` (→ `OcrOptions`).
- `Settings.from_env()` reads env vars through `_env` (empty string counts as unset) and `_env_bool`. `CHROMA_DIR` defaults to `DATA_DIR/chroma`.
- `get_settings()` is `@lru_cache(maxsize=1)`. It calls `load_dotenv()` (`.env` in the CWD) once, then `from_env()`. Tests call `Settings.from_env()` directly to avoid the cache.
- **To add a setting:** add a field to `Settings`, read it in `from_env` with a default, add it to `.env.example` and the README configuration table, add the field to `make_settings` in `tests/test_qa.py` (it builds `Settings` with every field), and assert the default in `tests/test_config.py`.
- `[AS-IS REALITY]` Paths are relative to the **current working directory** (`DATA_DIR=data`), and so is `.env`. Running from another directory silently uses or creates a different `data/`.
- `[AS-IS REALITY]` `ocr_mode` is only validated when `.ocr` is accessed (`OcrOptions.__post_init__`), not when `Settings` is built.
- `[AS-IS REALITY]` The OCR language default differs: `Settings` uses `eng+mar`, but `OcrOptions()` defaults to `lang="eng"`. Callers always pass `settings.ocr`.

## ingest.py: PDF → page records

| Function | Role |
|---|---|
| `clean(text)` | Removes NULs, collapses spaces and tabs, limits blank lines to one, strips. Run on all extracted text. |
| `looks_garbled(text)` | Devanagari font-mapping detector: ≥ `GARBLED_MIN_HITS` (3) double vowel-sign pairs **and** ≥ `GARBLED_PER_1000` (5.0) per 1000 Devanagari characters. |
| `resolve_ocr_lang(requested)` | `@lru_cache`. Keeps only the installed Tesseract packs and warns once. Returns `""` if Tesseract is missing (OCR disabled). |
| `table_as_text(page)` | pdfplumber tables → `a \| b` rows, tables separated by blank lines. |
| `_ocr(page, opts)` | Renders the page at `opts.dpi` → `pytesseract.image_to_string` → `clean`. |
| `extract_page(page, opts)` | **The OCR policy** (below). Returns `(text, method)`. |
| `extract_pdf(path, opts)` | One record per non-empty page. |
| `ingest_files(pdfs, pages_file, opts)` | Extracts the given PDFs and **merges** them into `pages_file`, replacing records with the same `source`. Returns only the new records. Used by the UI. |
| `ingest_dir(raw_dir, pages_file, opts)` | Extracts every `*.pdf` and **overwrites** `pages_file`. Raises `FileNotFoundError` if there are none. Used by the CLI. |
| `read_records` / `write_records` | JSONL I/O, UTF-8, `ensure_ascii=False`. |

**OCR policy in `extract_page`:**

| `OcrOptions.mode` | When OCR runs | When the OCR text is used |
|---|---|---|
| `never` | never | n/a |
| `auto` (default) | text is shorter than `MIN_TEXT_CHARS` (30), **or** `looks_garbled(text)` | short page: OCR text is longer · garbled page: OCR text is non-empty and not garbled |
| `always` | every page | OCR text is non-empty and not garbled |

When OCR is used the method is `"tesseract"` and pdfplumber tables are **not** appended. Otherwise tables are appended after a `\n\n[TABLE]\n` marker and the method is `"pdfplumber"`. OCR exceptions are logged and treated as an empty result.

- `[AS-IS REALITY]` `_DEVANAGARI` and `_DOUBLE_VOWEL_SIGN` contain **literal** Devanagari combining characters (U+0900–U+097F and U+093E–U+094C), not `\u` escapes. They're nearly invisible in editors, so edit those lines carefully or rewrite them with escapes.
- `[AS-IS REALITY]` `MIN_TEXT_CHARS`, `GARBLED_*` and the `[TABLE]` marker are module constants, not settings. Garbled detection only covers Devanagari.

## indexing.py: chunks and Chroma

| Function | Role |
|---|---|
| `records_to_documents(records)` | Records → langchain `Document`s, keeping the metadata. |
| `chunk_documents(docs, settings)` | `RecursiveCharacterTextSplitter(chunk_size, chunk_overlap)`. |
| `open_store(settings)` | Creates `chroma_dir` and returns a `Chroma` with `OllamaEmbeddings(embed_model, base_url)`. This is the only place a store is built. |
| `count_chunks(store)` | Number of ids in the collection. |
| `upsert_records(store, records, settings)` | For each `source` in `records`: delete its existing chunks (`store.get(where={"source": …})` → `store.delete(ids=…)`), then add the new chunks. This is **the** dedup mechanism. |
| `rebuild_index(settings)` | Reads `pages_file` (`FileNotFoundError` if empty), runs `delete_collection()`, reopens and upserts everything. |

- `[AS-IS REALITY]` `rebuild_index` drops the collection **before** embedding. If Ollama fails partway through, the index is left empty or partial until the next successful run.
- `[AS-IS REALITY]` Documents are identified only by **file name** (`metadata.source`). Two different PDFs with the same name overwrite each other, and deleting a PDF from `data/raw/` doesn't remove its chunks until `pdf-rag ingest && pdf-rag index`.

## qa.py: retrieval and answering

| Symbol | Role |
|---|---|
| `SYSTEM_PROMPT` | Answer only from context, say so when the answer is absent, cite as `[filename, p. N]`. |
| `strip_think(text)` | Removes `<think>…</think>` blocks (case-insensitive, multi-line) and everything before a lone `</think>` (R1's template opens the block itself). |
| `cite(doc)` | `[source, p. page]`, with `?` for missing metadata. The single citation formatter, also used by the UI. |
| `format_context(docs)` / `build_messages(question, docs)` | Prompt assembly → a single `[HumanMessage]`: `SYSTEM_PROMPT`, then `CONTEXT:`, then `QUESTION:`. There's no system message because DeepSeek-R1 follows instructions better without one. |
| `Answer` | Dataclass `text`, `sources: list[Document]`. |
| `RagPipeline(settings, store=None, llm=None)` | Builds the store (`open_store`) and `ChatOllama(model, base_url, temperature, reasoning, num_ctx)` unless they're injected. `retrieve` → `similarity_search(k=top_k)`. `ask`: an empty retrieval returns a fixed message **without** calling the LLM; otherwise it calls `invoke` and `strip_think`. |

- `RagPipeline`'s `store` and `llm` arguments exist so tests can inject fakes (`FakeStore`, `FakeLLM` in `tests/test_qa.py`). Keep new external calls injectable the same way.
- `LLM_REASONING=false` (the default) sends `think=false`, but `deepseek-r1:14b` reasons anyway (verified on Ollama 0.40.15, about 2.5k reasoning characters for a one-word reply). Ollama returns that reasoning in a separate `thinking` field, so `content` stays clean. `strip_think` is a safety net in case tags leak into `content`.
- `LLM_TEMPERATURE` defaults to `0.6` (DeepSeek's R1 recommendation) and `LLM_NUM_CTX` to `16384`. Ollama's default window silently truncates a prompt of top-k Devanagari chunks.
