from types import SimpleNamespace

import pytest

import pdf_rag.ingest as ingest
from pdf_rag.ingest import OcrOptions

# Real strings from a Maharashtra Assembly PDF: pdfplumber output (broken font
# mapping) vs. what the page actually says.
GARBLED = ("ताराांवित प्रश्नोत्तराांची यादी सोमिार, वदनाांि २३ माचच, "
           "याांचे प्रभारी विभाग, सािचजवन आरोग्य ि िुटुांब िल्याण मांत्री")
CORRECT = ("तारांकित प्रश्नोत्तरांची यादी सोमवार, दिनांक २३ मार्च, "
           "यांचे प्रभारी विभाग, सार्वजनिक आरोग्य व कुटुंब कल्याण मंत्री")


class FakePage:
    def __init__(self, text, tables=None, page_number=1):
        self._text = text
        self._tables = tables or []
        self.page_number = page_number

    def extract_text(self):
        return self._text

    def extract_tables(self):
        return self._tables

    def to_image(self, resolution):
        return SimpleNamespace(original=object())


@pytest.fixture
def fake_ocr(monkeypatch):
    """Make OCR return a fixed string without needing tesseract installed."""
    calls = []

    def install(result):
        def image_to_string(img, lang):
            calls.append(lang)
            if isinstance(result, Exception):
                raise result
            return result
        monkeypatch.setattr(ingest.pytesseract, "image_to_string", image_to_string)
        monkeypatch.setattr(ingest, "resolve_ocr_lang", lambda lang: lang)
        return calls

    return install


def test_clean_collapses_whitespace_and_nulls():
    assert ingest.clean("a\x00b   c\t\td\n\n\n\n\ne ") == "ab c d\n\ne"
    assert ingest.clean(None) == ""


def test_table_as_text_handles_none_cells():
    page = FakePage("", tables=[[["a", None], [" b ", "c"]], []])
    assert ingest.table_as_text(page) == "a | \nb | c"


def test_looks_garbled_detects_broken_devanagari():
    assert ingest.looks_garbled(GARBLED)
    assert not ingest.looks_garbled(CORRECT)
    assert not ingest.looks_garbled("Plain English text with no Devanagari at all.")


def test_ocr_options_rejects_unknown_mode():
    with pytest.raises(ValueError):
        OcrOptions(mode="sometimes")


def test_extract_page_uses_text_when_long_enough(fake_ocr):
    calls = fake_ocr("unused")
    assert ingest.extract_page(FakePage("x" * 50)) == ("x" * 50, "pdfplumber")
    assert calls == []


def test_extract_page_falls_back_to_ocr_for_empty_page(fake_ocr):
    fake_ocr("scanned text here")
    assert ingest.extract_page(FakePage("")) == ("scanned text here", "tesseract")


def test_extract_page_ocrs_garbled_text_and_drops_tables(fake_ocr):
    calls = fake_ocr(CORRECT)
    page = FakePage(GARBLED, tables=[[["ि", "ाां"]]])
    text, method = ingest.extract_page(page, OcrOptions(lang="eng+mar"))
    assert (text, method) == (CORRECT, "tesseract")
    assert calls == ["eng+mar"]


def test_extract_page_keeps_text_if_ocr_also_garbled(fake_ocr):
    fake_ocr(GARBLED)
    assert ingest.extract_page(FakePage(GARBLED)) == (GARBLED, "pdfplumber")


def test_extract_page_modes(fake_ocr):
    calls = fake_ocr("ocr text")
    assert ingest.extract_page(FakePage("x" * 50), OcrOptions(mode="always")) == ("ocr text", "tesseract")
    assert ingest.extract_page(FakePage(GARBLED), OcrOptions(mode="never")) == (GARBLED, "pdfplumber")
    assert len(calls) == 1


def test_extract_page_survives_ocr_failure(fake_ocr):
    fake_ocr(RuntimeError("tesseract not installed"))
    text, method = ingest.extract_page(FakePage("short", tables=[[["k", "v"]]]))
    assert method == "pdfplumber"
    assert text == "short\n\n[TABLE]\nk | v"


def test_resolve_ocr_lang_drops_missing_packs(monkeypatch):
    ingest.resolve_ocr_lang.cache_clear()
    monkeypatch.setattr(ingest.pytesseract, "get_languages", lambda config: ["eng", "osd"])
    try:
        assert ingest.resolve_ocr_lang("eng+mar") == "eng"
    finally:
        ingest.resolve_ocr_lang.cache_clear()


def test_ingest_files_replaces_records_for_same_source(tmp_path, monkeypatch):
    pages_file = tmp_path / "pages.jsonl"
    ingest.write_records(pages_file, [
        {"text": "old", "metadata": {"source": "a.pdf", "page": 1}},
        {"text": "keep", "metadata": {"source": "b.pdf", "page": 1}},
    ])
    monkeypatch.setattr(ingest, "extract_pdf", lambda p, opts: [
        {"text": "new", "metadata": {"source": p.name, "page": 1}}
    ])
    new = ingest.ingest_files([tmp_path / "a.pdf"], pages_file)
    assert [r["text"] for r in new] == ["new"]
    assert sorted(r["text"] for r in ingest.read_records(pages_file)) == ["keep", "new"]
