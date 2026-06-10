"""Confidence scoring + routing tests."""

from ocr_statement.models import LineItem
from ocr_statement.scoring import (
    CONFIDENCE_THRESHOLD,
    needs_review,
    score,
)


def _item(**overrides) -> LineItem:
    base = dict(
        line_number=1,
        date="2024-03-10",
        description="desc",
        category="Mitigation",
        quantity=1,
        unit_amount_cents=1000,
        total_amount_cents=1000,
        field_confidences={
            "date": 0.97,
            "unit_amount_cents": 0.97,
            "total_amount_cents": 0.97,
        },
    )
    base.update(overrides)
    return LineItem(**base)


def test_clean_row_scores_high_and_accepts():
    item = _item()
    s = score(item)
    assert s >= CONFIDENCE_THRESHOLD
    assert not needs_review(item)


def test_low_confidence_field_routes_to_review():
    item = _item(field_confidences={
        "date": 0.97,
        "unit_amount_cents": 0.55,   # faint print
        "total_amount_cents": 0.55,
    })
    score(item)
    assert needs_review(item)


def test_uses_minimum_not_mean():
    # One weak field should drag the row down even if others are perfect.
    item = _item(field_confidences={
        "date": 0.99,
        "unit_amount_cents": 0.99,
        "total_amount_cents": 0.50,
    })
    score(item)
    assert item.confidence <= 0.50 + 1e-9


def test_arithmetic_mismatch_penalized_even_with_high_ocr_conf():
    # High OCR confidence but qty*unit != total (digit transposition).
    item = _item(
        quantity=220,
        unit_amount_cents=1150,
        total_amount_cents=235000,  # truth would be 253000
        field_confidences={
            "date": 0.97,
            "unit_amount_cents": 0.97,
            "total_amount_cents": 0.97,
        },
    )
    score(item)
    assert "arithmetic_mismatch" in item.flags
    assert needs_review(item)


def test_missing_total_penalized():
    item = _item(total_amount_cents=None, field_confidences={
        "date": 0.97,
        "unit_amount_cents": 0.97,
    })
    score(item)
    assert "missing_total" in item.flags
    assert needs_review(item)
