"""End-to-end orchestration.

    PDF -> OCR -> parse -> validate (schema gate) -> score -> route
        -> ExtractionResult (accepted / review_queue / rejected)

The order matters and encodes the two-gate policy:

1. Schema validation first. A structurally broken row (no date, negative total,
   non-ISO date) is *rejected* no matter how confident the OCR was. There is no
   point asking a human to "review" a row we can't represent.

2. Confidence routing second. Among structurally-valid rows, anything below the
   threshold is sent to the review queue rather than silently accepted.
"""

from __future__ import annotations

from typing import Optional

from .models import ExtractionResult
from .ocr import OCREngine, get_default_engine
from .parser import parse
from .schema import validate_line_item
from .scoring import CONFIDENCE_THRESHOLD, score


def run_pipeline(
    pdf_path: str,
    engine: Optional[OCREngine] = None,
    threshold: float = CONFIDENCE_THRESHOLD,
    is_synthetic: bool = True,
) -> ExtractionResult:
    """Run the full extraction pipeline and return a structured result."""
    engine = engine or get_default_engine()

    ocr_result = engine.run(pdf_path)
    items, _phantoms = parse(ocr_result)

    result = ExtractionResult(
        source_document=pdf_path,
        is_synthetic=is_synthetic,
        page_count=ocr_result.page_count,
        confidence_threshold=threshold,
    )

    for item in items:
        # Gate 1: schema validation.
        errors = validate_line_item(item)
        if errors:
            payload = item.to_dict()
            payload["validation_errors"] = errors
            result.rejected.append(payload)
            continue

        # Gate 2: confidence routing.
        score(item)
        if item.confidence < threshold:
            result.review_queue.append(item)
        else:
            result.accepted.append(item)

    return result
