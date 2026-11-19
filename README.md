# PDF RAG Assistant (DeepSeek-R1 edition)

Ask questions about your own PDFs and get answers with page citations, all running locally. Text is pulled from the PDFs (with OCR for scanned pages and table extraction), embedded with **bge-m3**, stored in **ChromaDB**, and answered by **DeepSeek-R1 14B** (`deepseek-r1:14b`) through **Ollama**. No data leaves your machine and no API keys are needed.

This is a copy of the Qwen3 project (`pdf_rag_qwen14_upgrade`) adapted for DeepSeek-R1. It keeps its own index in its own `data/` folder; see [What changed for DeepSeek](#what-changed-for-deepseek).

You can use it from the command line (`pdf-rag`) or through a Streamlit chat UI where you can also upload new PDFs.

## Architecture

```
            ┌──────────────┐   pages.jsonl   ┌──────────────┐  embeddings  ┌──────────┐
data/raw/ ─▶│  ingest.py   │────────────────▶│ indexing.py  │─────────────▶│ ChromaDB │
  *.pdf     │ pdfplumber   │ data/processed/ │ chunk 1000/150│  (bge-m3)   │data/chroma│
            │ + Tesseract  │                 └──────────────┘              └────┬─────┘
            │ + tables     │                                                    │ top-k
            └──────────────┘                                                    ▼
                                    question ──▶ ┌──────────────┐  prompt  ┌───────────┐
                     CLI / Streamlit ◀── answer ─│    qa.py     │─────────▶│deepseek-r1│
                                    + sources    │ RagPipeline  │◀─────────│:14b Ollama│
                                                 └──────────────┘          └───────────┘
```

1. **Ingest** (`pdf_rag.ingest`): reads each page with pdfplumber. A page is run through Tesseract OCR instead when it has almost no text (a scan) or when its text looks **garbled** (see [Marathi and other Devanagari PDFs](#marathi-and-other-devanagari-pdfs)). Tables from pages that weren't OCR'd are added as `a | b | c` rows under a `[TABLE]` marker. Each page becomes one JSON line with `source`, `page` and `method` (`pdfplumber` or `tesseract`) metadata.
2. **Index** (`pdf_rag.indexing`): splits pages into overlapping chunks, embeds them with bge-m3 and stores them in a persistent Chroma collection. Re-indexing a file replaces its old chunks, so nothing is duplicated.
3. **Answer** (`pdf_rag.qa`): retrieves the top-k chunks for a question and asks DeepSeek-R1 to answer **only** from that context, citing `[filename, p. N]`. R1's `<think>` reasoning (including the dangling `</think>` R1 often emits) is removed before the answer is shown.

## Repository layout

```
├── src/pdf_rag/
│   ├── config.py       # settings from environment / .env
│   ├── ingest.py       # PDF → page records (text, OCR, tables)
│   ├── indexing.py     # chunking + Chroma index management
│   ├── qa.py           # retrieval + prompting (RagPipeline)
│   └── cli.py          # `pdf-rag` command
├── app/streamlit_app.py  # chat UI with PDF upload
├── tests/                # unit tests (no Ollama needed)
├── data/
│   ├── raw/            # your PDFs        (git-ignored)
│   ├── processed/      # pages.jsonl      (git-ignored)
│   └── chroma/         # vector store     (git-ignored)
├── .env.example
├── pyproject.toml
└── requirements.txt
```

## Setup

Requires macOS or Linux, Python 3.10+, and [Ollama](https://ollama.com).

```bash
# 1. Models (deepseek-r1:14b is a ~9 GB download and needs about 12 GB of RAM at the
#    default 16k context; see "Configuration" for a lighter one)
ollama pull deepseek-r1:14b
ollama pull bge-m3

# 2. OCR, for scanned or Marathi PDFs (optional, but recommended)
brew install tesseract tesseract-lang     # Debian/Ubuntu: sudo apt install tesseract-ocr tesseract-ocr-mar

# 3. Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"           # or: pip install -r requirements.txt && pip install -e .

# 4. Optional: configuration
cp .env.example .env
```

Make sure Ollama is running (`ollama list` should show `deepseek-r1:14b` and `bge-m3`) before indexing or asking questions. To check the chat model on its own:

```bash
ollama run deepseek-r1:14b "Reply with OK"
```

## Configuration

All settings come from environment variables or a `.env` file in the directory you run from. Every setting is optional.

| Variable | Default | Purpose |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server |
| `LLM_MODEL` | `deepseek-r1:14b` | Chat model (e.g. `deepseek-r1:8b` for less memory, `deepseek-r1:32b` for better answers on ≥32 GB) |
| `LLM_TEMPERATURE` | `0.6` | Sampling temperature. DeepSeek recommends 0.5–0.7 for R1; lower values can cause repetition |
| `LLM_REASONING` | `false` | Ollama's think switch. `deepseek-r1` reasons regardless, so it has no visible effect with R1; it's kept for other models |
| `LLM_NUM_CTX` | `16384` | Context window in tokens. The prompt (top-k chunks; Devanagari uses many tokens) plus the answer must fit, or Ollama silently truncates |
| `EMBED_MODEL` | `bge-m3` | Embedding model |
| `DATA_DIR` | `data` | Root for `raw/` and `processed/` |
| `CHROMA_DIR` | `$DATA_DIR/chroma` | Vector store location |
| `COLLECTION_NAME` | `pdf_rag` | Chroma collection |
| `OCR_LANG` | `eng+mar` | Tesseract languages, joined with `+`; packs that aren't installed are skipped with a warning |
| `OCR_MODE` | `auto` | `auto`: OCR pages with little or garbled text · `always`: OCR every page · `never`: no OCR |
| `OCR_DPI` | `300` | Resolution of the page images used for OCR |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `1000` / `150` | Text splitting, in characters |
| `TOP_K` | `5` | Chunks retrieved per question |

Changing `EMBED_MODEL`, `CHUNK_SIZE` or `CHUNK_OVERLAP` requires running `pdf-rag index` again. Changing an `OCR_*` setting requires running `pdf-rag ingest` and then `pdf-rag index`.

### Marathi and other Devanagari PDFs

Many Indian government PDFs use fonts whose embedded text maps to the wrong Unicode characters. The page looks fine on screen, but the extracted text is wrong: `पवहले अवधिेशन` instead of `पहिले अधिवेशन`, `िैद्यिीय वशक्षण` instead of `वैद्यकीय शिक्षण`. That makes retrieval worse and leads the model to mistranslate. In one test, "Medical Education" came back as "Health and Family Welfare".

In `auto` mode, ingestion spots this by counting two vowel signs in a row (such as `ाां`), which never happen in valid text. Broken pages score about 25–35 per 1,000 Devanagari characters and correct text scores about 0. Pages that cross the threshold are OCR'd with `OCR_LANG`. You need the Marathi language pack installed (`tesseract-lang` above). Without it, the page keeps its extracted text and a warning is printed.

OCR takes about 3 s per page at 300 dpi, compared with milliseconds for plain text extraction.

## What changed for DeepSeek

Compared with the Qwen3 project:

- **Model:** `LLM_MODEL` defaults to `deepseek-r1:14b`. The embedding model is still `bge-m3`, so retrieval behaves the same.
- **Prompt:** DeepSeek advises against a system prompt for R1, so the instructions (answer only from context, cite `[filename, p. N]`) go at the top of the single user message, followed by the context and the question.
- **Thinking:** `<think>…</think>` blocks are removed, and so is everything before a lone `</think>`. R1's chat template opens the block itself, so often only the closing tag shows up in the output. R1 always reasons, even with `LLM_REASONING=false` (tested on Ollama 0.40.15). Ollama returns the reasoning separately and it is never shown, but it does cost time: about 35 s even for a one-word reply.
- **Sampling and context:** temperature 0.6 (DeepSeek's recommendation) and an explicit 16k-token context window (`LLM_NUM_CTX`), because Ollama's default window is too small for five Marathi chunks.
- **Data:** the index is not shared with the Qwen project. Run `pdf-rag ingest` and `pdf-rag index` once in this folder.

## Usage

### Command line

```bash
cd pdf_rag_deepseek && source .venv/bin/activate
cp ~/Downloads/*.pdf data/raw/

pdf-rag ingest          # extract text   → data/processed/pages.jsonl
pdf-rag index           # embed + store  → data/chroma/
pdf-rag ask "What is the session date?"
pdf-rag chat            # interactive; type `exit` or press Ctrl-D to quit
```

Example output:

```
$ pdf-rag ask "What date is this session?"

The date of the session is March 23, 2026 [MAR23-ASSEMBLY.pdf, p. 1].

Retrieved sources:
- MAR23-ASSEMBLY.pdf page 1
- MAR23-ASSEMBLY.pdf page 8
...
```

Add `-v` to any command to see progress logs. `python -m pdf_rag ...` works too.

### Web UI

```bash
streamlit run app/streamlit_app.py
```

Upload PDFs in the sidebar and click **Index**. They are saved to `data/raw/`, extracted and added to the index. Then ask questions in the chat. Each answer has a **Sources** section listing the pages it was built from.

### From Python

```python
from pdf_rag.config import get_settings
from pdf_rag.qa import RagPipeline

answer = RagPipeline(get_settings()).ask("Which ministers are listed?")
print(answer.text)
for doc in answer.sources:
    print(doc.metadata["source"], doc.metadata["page"])
```

## Testing

```bash
pytest
```

The unit tests replace Ollama, Chroma and Tesseract with fakes, so they run without any models installed.

## Known limitations

- Garbled-text detection only covers Devanagari. Broken font mappings in other scripts need `OCR_MODE=always`.
- OCR output still has occasional single-character errors (e.g. `व` read as `a` or `ब`).
- `pdf-rag ingest` and `pdf-rag index` rebuild everything from scratch. The web UI's upload adds or replaces individual files instead.
- Retrieval is plain vector similarity, with no reranking or hybrid keyword search.
