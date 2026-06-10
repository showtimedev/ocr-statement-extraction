"""Confidence scoring + the human-in-the-loop threshold router.

The aggregate row confidence combines two signals:

1. OCR signal  - the minimum per-field confidence among the fields that matter
   most for a financial row (date, amounts). We use the *minimum*, not the mean,
   because one badly-read amount is enough to make the whole row untrustworthy
   even if everything else read cleanly. Means hide exactly the failures we care
   about.

2. Consistency signal - business-logic checks that don't depend on OCR
   confidence at all: does quantity * unit == total? is the total plausible?
   A digit transposition can read with high OCR confidence yet still be wrong;
   the arithmetic check is what catches it. When a consistency check fails we
   apply a penalty so the row drops below threshold and gets human eyes.

route() then splits rows on a single, visible CONFIDENCE_THRESHOLD.
"""

from __future__ import annotations

from .models import LineItem

# The one knob that matters. Rows at or above this are auto-accepted; below it
# they go to the review queue. Surfaced in the CLI and the output JSON so the
# threshold is never hidden inside the code.
CONFIDENCE_THRESHOLD = 0.85

# Fields whose OCR confidence gates the row. A weak read on any of these is
# enough to demand review.
CRITICAL_FIELDS = ("date", "total_amount_cents", "unit_amount_cents")

# Penalties applied to the aggregate score when a consistency check fails.
ARITHMETIC_MISMATCH_PENALTY = 0.40
MISSING_CRITICAL_PENALTY = 0.50


def score(item: LineItem) -> float:
    """Compute and attach an aggregate confidence in [0, 1] to `item`.

    Side effects: sets item.confidence and may append consistency flags. Returns
    the score for convenience.
    """
    # --- OCR signal: minimum confidence across present critical fields ----
    present = [
        item.field_confidences[f]
        for f in CRITICAL_FIELDS
        if f in item.field_confidences
    ]
    ocr_signal = min(present) if present else 0.0

    score_val = ocr_signal

    # --- Consistency signal: arithmetic check ----------------------------
    if (
        item.quantity is not None
        and item.unit_amount_cents is not None
        and item.total_amount_cents is not None
    ):
        expected = round(item.quantity * item.unit_amount_cents)
        if expected != item.total_amount_cents:
            if "arithmetic_mismatch" not in item.flags:
                item.flags.append("arithmetic_mismatch")
            score_val -= ARITHMETIC_MISMATCH_PENALTY

    # Missing a critical amount is a real problem even if OCR was confident
    # about what little it did read.
    if item.total_amount_cents is None:
        if "missing_total" not in item.flags:
            item.flags.append("missing_total")
        score_val -= MISSING_CRITICAL_PENALTY

    score_val = max(0.0, min(1.0, score_val))
    item.confidence = round(score_val, 4)
    return item.confidence


def needs_review(item: LineItem, threshold: float = CONFIDENCE_THRESHOLD) -> bool:
    return item.confidence < threshold
