"""End-to-end pipeline tests."""

from ocr_statement.pipeline import run_pipeline
from ocr_statement.scoring import CONFIDENCE_THRESHOLD


def test_pipeline_runs_end_to_end():
    result = run_pipeline("dummy.pdf")
    assert result.is_synthetic is True
    assert result.page_count >= 2
    # Every parsed row lands in exactly one bucket.
    total = len(result.accepted) + len(result.review_queue) + len(result.rejected)
    assert total == 12


def test_injected_failures_land_in_review_queue():
    result = run_pipeline("dummy.pdf")
    review_lines = {i.line_number for i in result.review_queue}

    # Row 3 = digit transposition (arithmetic mismatch).
    assert 3 in review_lines
    # Row 5 = low-confidence faint money fields.
    assert 5 in review_lines


def test_arithmetic_mismatch_flag_surfaced_in_review():
    result = run_pipeline("dummy.pdf")
    row3 = next(i for i in result.review_queue if i.line_number == 3)
    assert "arithmetic_mismatch" in row3.flags


def test_clean_rows_are_accepted():
    result = run_pipeline("dummy.pdf")
    accepted_lines = {i.line_number for i in result.accepted}
    # Row 1 is clean and should auto-accept.
    assert 1 in accepted_lines
    for item in result.accepted:
        assert item.confidence >= CONFIDENCE_THRESHOLD


def test_threshold_is_tunable():
    strict = run_pipeline("dummy.pdf", threshold=0.99)
    lax = run_pipeline("dummy.pdf", threshold=0.0)
    # A stricter threshold sends at least as many rows to review.
    assert len(strict.review_queue) >= len(lax.review_queue)
    # With threshold 0, nothing valid should be sent to review.
    assert len(lax.review_queue) == 0


def test_result_serializes_to_dict():
    result = run_pipeline("dummy.pdf")
    d = result.to_dict()
    assert d["summary"]["accepted"] == len(result.accepted)
    assert d["is_synthetic"] is True
    assert "confidence_threshold" in d
