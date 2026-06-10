"""Command-line entry point.

    python -m ocr_statement.cli [PDF] [--threshold T] [--out DIR]

Writes:
    <out>/extraction_result.json        full structured result
    <out>/review_queue/<n>.json         one file per low-confidence row

If no PDF is given (or the default path is missing) the synthetic PDF is
generated first so the demo always runs end-to-end with zero setup.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .generate_pdf import DEFAULT_OUTPUT as DEFAULT_PDF
from .generate_pdf import generate
from .pipeline import run_pipeline
from .scoring import CONFIDENCE_THRESHOLD


def _ensure_pdf(pdf_path: str) -> str:
    if os.path.exists(pdf_path):
        return pdf_path
    print(f"[info] {pdf_path} not found - generating synthetic PDF...")
    try:
        return generate(pdf_path)
    except RuntimeError as exc:
        print(f"[warn] could not generate PDF ({exc}).")
        print("[warn] continuing with the synthetic OCR engine, which does not "
              "actually read the PDF file.")
        return pdf_path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="OCR Statement-of-Loss extraction pipeline")
    parser.add_argument("pdf", nargs="?", default=DEFAULT_PDF, help="path to the statement PDF")
    parser.add_argument(
        "--threshold",
        type=float,
        default=CONFIDENCE_THRESHOLD,
        help=f"confidence threshold for auto-accept (default {CONFIDENCE_THRESHOLD})",
    )
    parser.add_argument("--out", default="output", help="output directory")
    args = parser.parse_args(argv[1:])

    pdf_path = _ensure_pdf(args.pdf)

    result = run_pipeline(pdf_path, threshold=args.threshold)

    review_dir = os.path.join(args.out, "review_queue")
    os.makedirs(review_dir, exist_ok=True)

    # Full result.
    result_path = os.path.join(args.out, "extraction_result.json")
    with open(result_path, "w") as fh:
        json.dump(result.to_dict(), fh, indent=2)

    # One file per review-queue row, so a reviewer can claim them individually.
    for item in result.review_queue:
        path = os.path.join(review_dir, f"line_{item.line_number:03d}.json")
        with open(path, "w") as fh:
            json.dump(item.to_dict(), fh, indent=2)

    _print_summary(result, result_path, review_dir)
    return 0


def _print_summary(result, result_path: str, review_dir: str) -> None:
    print("\n=== Extraction summary ===")
    print(f"source        : {result.source_document}")
    print(f"synthetic     : {result.is_synthetic}")
    print(f"pages         : {result.page_count}")
    print(f"threshold     : {result.confidence_threshold}")
    print(f"accepted      : {len(result.accepted)}")
    print(f"review_queue  : {len(result.review_queue)}")
    print(f"rejected      : {len(result.rejected)}")
    print(f"\nfull result   -> {result_path}")
    print(f"review queue  -> {review_dir}/")

    if result.review_queue:
        print("\nrows routed to review:")
        for item in result.review_queue:
            flags = ", ".join(item.flags) or "low confidence"
            print(f"  line {item.line_number}: conf={item.confidence:.2f} ({flags})")
    if result.rejected:
        print("\nrows rejected (schema):")
        for row in result.rejected:
            print(f"  line {row.get('line_number')}: {row.get('validation_errors')}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv))
