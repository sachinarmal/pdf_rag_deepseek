"""Command line entry point: `pdf-rag {ingest,index,chat,ask}`."""

from __future__ import annotations

import argparse
import logging
import sys

from .config import get_settings


def cmd_ingest(args) -> int:
    from .ingest import ingest_dir

    s = get_settings()
    records = ingest_dir(s.raw_dir, s.pages_file, s.ocr)
    n_ocr = sum(r["metadata"]["method"] == "tesseract" for r in records)
    print(f"Saved {len(records)} page records ({n_ocr} via OCR) -> {s.pages_file}")
    return 0


def cmd_index(args) -> int:
    from .indexing import rebuild_index

    s = get_settings()
    n = rebuild_index(s)
    print(f"Indexed {n} chunks into {s.chroma_dir} (collection '{s.collection_name}')")
    return 0


def _print_answer(answer) -> None:
    print("\n" + answer.text)
    if answer.sources:
        print("\nRetrieved sources:")
        for d in answer.sources:
            print(f"- {d.metadata.get('source')} page {d.metadata.get('page')}")


def cmd_ask(args) -> int:
    from .qa import RagPipeline

    _print_answer(RagPipeline(get_settings()).ask(" ".join(args.question)))
    return 0


def cmd_chat(args) -> int:
    from .qa import RagPipeline

    pipeline = RagPipeline(get_settings())
    while True:
        try:
            question = input("\nQuestion (or exit): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if question.lower() in {"exit", "quit"}:
            return 0
        if question:
            _print_answer(pipeline.ask(question))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pdf-rag", description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true", help="show progress logs")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ingest", help="extract text from data/raw/*.pdf").set_defaults(func=cmd_ingest)
    sub.add_parser("index", help="(re)build the Chroma index").set_defaults(func=cmd_index)
    sub.add_parser("chat", help="interactive Q&A").set_defaults(func=cmd_chat)
    ask = sub.add_parser("ask", help="answer one question and exit")
    ask.add_argument("question", nargs="+")
    ask.set_defaults(func=cmd_ask)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
