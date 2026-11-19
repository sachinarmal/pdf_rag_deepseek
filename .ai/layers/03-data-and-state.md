# Layer 3: Data and state

All persistent data is local files under `DATA_DIR` (default `data/`, relative to the CWD). Everything except the `.gitkeep` files is git-ignored. There is no other database, cache or remote storage.

```
data/raw/*.pdf  ──ingest──▶  data/processed/pages.jsonl  ──index──▶  data/chroma/  ──retrieve──▶  answer
 (source files)   ingest.py      (page records)            indexing.py  (vectors)       qa.py
```

## 1. `data/raw/`: source PDFs

- Written by the user (copying files in) or by the Streamlit upload (`app/streamlit_app.py`, `settings.raw_dir / Path(f.name).name`).
- Read by `ingest.ingest_dir` (`*.pdf`, sorted) and `ingest.ingest_files` (explicit paths).
- The **file name is the document's identity** everywhere downstream (`metadata.source`).

## 2. `data/processed/pages.jsonl`: page records

One JSON object per line, UTF-8, one per **non-empty** page:

```json
{"text": "<cleaned page text, optionally + \"\\n\\n[TABLE]\\n\" + tables>",
 "metadata": {"source": "MAR23-ASSEMBLY.pdf", "page": 1, "method": "tesseract"}}
```

| Field | Type | Notes |
|---|---|---|
| `text` | str | Output of `clean()`. OCR'd pages never contain `[TABLE]` |
| `metadata.source` | str | PDF file name, no directory |
| `metadata.page` | int | 1-based page number |
| `metadata.method` | `"pdfplumber"` \| `"tesseract"` | How the text was obtained |

- **Write:** `write_records` always rewrites the whole file. `ingest_dir` replaces everything; `ingest_files` keeps records from other sources and replaces the given ones.
- **Read:** `read_records` (a missing file returns `[]`). Used by `indexing.rebuild_index` and `ingest.ingest_files`.

## 3. `data/chroma/`: vector store

- Opened only through `indexing.open_store`. The collection is `COLLECTION_NAME` (default `pdf_rag`), the embedding function is `OllamaEmbeddings(EMBED_MODEL)`.
- One entry per chunk: `document` = chunk text (≤ `CHUNK_SIZE` characters, `CHUNK_OVERLAP` overlap), `metadata` = **the page record's metadata copied verbatim** (`source`, `page`, `method`), and `id` = a random UUID assigned by langchain-chroma.
- **Write:** `upsert_records` (delete by `where={"source": …}`, then `add_documents`) and `rebuild_index` (`delete_collection`, then upsert all).
- **Read:** `RagPipeline.retrieve` (`similarity_search`) and `count_chunks`.
- The metadata keys are a contract: `upsert_records` filters on `source`, and `qa.cite` and `cli._print_answer` read `source` and `page`.

### Migrations and compatibility

There is **no migration mechanism and no schema version** in either `pages.jsonl` or the Chroma metadata. The current way to "migrate" is to regenerate:

- If the extraction or OCR logic or any `OCR_*` setting changes, run `pdf-rag ingest`, then `pdf-rag index`.
- If `EMBED_MODEL`, `CHUNK_SIZE` or `CHUNK_OVERLAP` changes, run `pdf-rag index`.

- `[AS-IS REALITY]` Nothing detects that an existing index was built with a different embedding model or chunk size. Mixing them gives wrong retrieval with no error.
- `[AS-IS REALITY]` `pages.jsonl` and Chroma can drift apart: running `pdf-rag ingest` without `index`, a UI upload that fails after `ingest_files` but before `upsert_records`, or a `rebuild_index` that fails halfway.
- `[AS-IS REALITY]` `delete_collection()` leaves orphaned segment folders under `data/chroma/` (2 UUID folders exist after one rebuild). It's harmless, but the folder keeps growing.

## 4. In-memory and process state

| State | Where | Lifetime |
|---|---|---|
| `Settings` | `config.get_settings` (`lru_cache`) | process: env changes after the first call are ignored |
| Installed OCR languages | `ingest.resolve_ocr_lang` (`lru_cache`) | process |
| `RagPipeline` (store + LLM client) | `app/streamlit_app.py` `get_pipeline` (`st.cache_resource`) | Streamlit server process, **shared by all browser sessions** |

## 5. Frontend state (Streamlit)

- `st.session_state.messages`: per browser session, `list[dict]` with `{"role": "user"|"assistant", "content": str, "sources": list[str]}` (`sources` only on assistant turns; the values are `cite()` strings). It's cleared by "Clear chat" and lost on page reload. It isn't persisted.
- The uploader widget state is Streamlit's own. Uploaded bytes are written to `data/raw/` only when "Index" is clicked.
