"""Tests for the synthetic OCR engine: noise is injected as designed."""

from ocr_statement.ocr import SyntheticOCREngine
from ocr_statement.sample_data import SOURCE_ROWS


def test_engine_is_deterministic():
    a = SyntheticOCREngine().run("dummy.pdf")
    b = SyntheticOCREngine().run("dummy.pdf")
    assert [ln.text for ln in a.lines] == [ln.text for ln in b.lines]


def test_engine_reports_multiple_pages():
    result = SyntheticOCREngine().run("dummy.pdf")
    assert result.page_count >= 2  # 12 rows / 7 per page -> 2 pages


def test_low_confidence_token_present():
    # Row 5 should contain a sub-0.6 money token (faint print simulation).
    result = SyntheticOCREngine().run("dummy.pdf")
    low = [t for ln in result.lines for t in ln.tokens if t.confidence < 0.6]
    assert low, "expected at least one low-confidence token from injected noise"


def test_digit_transposition_injected():
    # Row 3 total should differ from the ground-truth formatted total.
    from ocr_statement.ocr import _money_str

    result = SyntheticOCREngine().run("dummy.pdf")
    row3 = SOURCE_ROWS[2]
    truth_total = _money_str(row3.total_amount_cents)
    # Find the data line that starts with line number 3.
    line3 = next(
        ln for ln in result.lines if ln.tokens and ln.tokens[0].text == "3"
    )
    money_tokens = [t.text for t in line3.tokens if t.text.startswith("$")]
    assert money_tokens[-1] != truth_total, "expected transposed total on row 3"
