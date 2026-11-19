"""Extract text (with OCR fallback and tables) from PDFs into page records."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pdfplumber
import pytesseract

log = logging.getLogger(__name__)

# Pages whose extracted text is shorter than this are treated as scans and OCR'd.
MIN_TEXT_CHARS = 30

# Garbled-text detection for Devanagari (Marathi/Hindi). PDFs with legacy or
# badly mapped fonts yield text with impossible sequences such as two vowel
# signs in a row ("ाां"). Correct text has ~0 of these per 1000 characters;
# broken pages measured 24-36.
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_DOUBLE_VOWEL_SIGN = re.compile(r"[ा-ौ][ा-ौ]")
GARBLED_PER_1000 = 5.0
GARBLED_MIN_HITS = 3

OCR_MODES = ("auto", "always", "never")


@dataclass(frozen=True)
class OcrOptions:
    lang: str = "eng"
    mode: str = "auto"   # auto: OCR pages with little or garbled text; always; never
    dpi: int = 300

    def __post_init__(self):
        if self.mode not in OCR_MODES:
            raise ValueError(f"OCR mode must be one of {OCR_MODES}, got {self.mode!r}")


def clean(text: str | None) -> str:
    text = (text or "").replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def looks_garbled(text: str) -> bool:
    """True if Devanagari text contains many impossible vowel-sign sequences."""
    hits = len(_DOUBLE_VOWEL_SIGN.findall(text))
    if hits < GARBLED_MIN_HITS:
        return False
    dev_chars = len(_DEVANAGARI.findall(text))
    return 1000 * hits / max(dev_chars, 1) >= GARBLED_PER_1000


@lru_cache(maxsize=None)
def resolve_ocr_lang(requested: str) -> str:
    """Drop language packs that tesseract does not have, warning once."""
    try:
        available = set(pytesseract.get_languages(config=""))
    except Exception as exc:  # tesseract binary missing
        log.warning("Tesseract unavailable, OCR disabled: %s", exc)
        return ""
    wanted = [l for l in requested.split("+") if l]
    missing = [l for l in wanted if l not in available]
    if missing:
        log.warning("Tesseract language pack(s) not installed, skipping: %s", ", ".join(missing))
    return "+".join(l for l in wanted if l in available)


def table_as_text(page) -> str:
    tables = []
    for table in page.extract_tables() or []:
        if table:
            tables.append("\n".join(
                " | ".join((str(c).strip() if c is not None else "") for c in row)
                for row in table
            ))
    return "\n\n".join(tables)


def _ocr(page, opts: OcrOptions) -> str:
    lang = resolve_ocr_lang(opts.lang)
    if not lang:
        return ""
    image = page.to_image(resolution=opts.dpi).original
    return clean(pytesseract.image_to_string(image, lang=lang))


def extract_page(page, opts: OcrOptions = OcrOptions()) -> tuple[str, str]:
    """Return (text, method) for one pdfplumber page; method is pdfplumber or tesseract."""
    text = clean(page.extract_text())

    reason = None
    if opts.mode == "always":
        reason = "forced"
    elif opts.mode == "auto":
        if len(text) < MIN_TEXT_CHARS:
            reason = "little text"
        elif looks_garbled(text):
            reason = "garbled text"

    if reason:
        try:
            ocr = _ocr(page, opts)
        except Exception as exc:
            log.warning("OCR failed on page %s (%s): %s", page.page_number, reason, exc)
            ocr = ""
        if reason == "little text":
            use_ocr = len(ocr) > len(text)
        else:  # forced or garbled: prefer OCR unless it produced nothing usable
            use_ocr = bool(ocr) and not looks_garbled(ocr)
        if use_ocr:
            log.info("Page %s: using OCR (%s)", page.page_number, reason)
            # pdfplumber tables carry the same bad/absent text, and OCR
            # already contains the table contents as lines.
            return ocr, "tesseract"
        if reason == "garbled text":
            log.warning("Page %s looks garbled but OCR did not help; keeping extracted text",
                        page.page_number)

    tables = clean(table_as_text(page))
    if tables:
        text = (text + "\n\n[TABLE]\n" + tables).strip()
    return text, "pdfplumber"


def extract_pdf(path: Path, opts: OcrOptions = OcrOptions()) -> list[dict]:
    """Return one record per non-empty page: {"text": ..., "metadata": {...}}."""
    records = []
    log.info("Reading %s", path.name)
    with pdfplumber.open(path) as pdf:
        for page_no, page in enumerate(pdf.pages, 1):
            text, method = extract_page(page, opts)
            if text:
                records.append({"text": text, "metadata": {
                    "source": path.name, "page": page_no, "method": method,
                }})
    return records


def read_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_records(path: Path, records: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def ingest_files(pdfs: Iterable[Path], pages_file: Path,
                 opts: OcrOptions = OcrOptions()) -> list[dict]:
    """Extract the given PDFs and merge them into pages_file.

    Existing records for the same file names are replaced, so re-ingesting a
    file does not create duplicates. Returns only the new records.
    """
    new_records: list[dict] = []
    sources: set[str] = set()
    for pdf in pdfs:
        new_records.extend(extract_pdf(pdf, opts))
        sources.add(pdf.name)
    kept = [r for r in read_records(pages_file) if r["metadata"]["source"] not in sources]
    write_records(pages_file, kept + new_records)
    return new_records


def ingest_dir(raw_dir: Path, pages_file: Path, opts: OcrOptions = OcrOptions()) -> list[dict]:
    """Extract every PDF in raw_dir, replacing pages_file entirely."""
    pdfs = sorted(raw_dir.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No PDFs found in {raw_dir}/")
    records = [r for pdf in pdfs for r in extract_pdf(pdf, opts)]
    write_records(pages_file, records)
    return records
