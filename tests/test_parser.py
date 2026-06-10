"""Parser tests, including the page-break phantom-row edge case."""

from ocr_statement.models import OCRLine, OCRResult, Token
from ocr_statement.ocr import SyntheticOCREngine
from ocr_statement.parser import parse, _looks_like_phantom


def _parse_synthetic():
    ocr = SyntheticOCREngine().run("dummy.pdf")
    return parse(ocr)


def test_parses_all_real_rows():
    items, _ = _parse_synthetic()
    # 12 ground-truth rows; all should be parsed as data rows.
    assert len(items) == 12
    assert [i.line_number for i in items] == list(range(1, 13))


def test_page_break_phantom_row_is_dropped():
    """The page-break phantom partial row must NOT become a line item."""
    items, phantoms = _parse_synthetic()

    # At least one phantom fragment was detected and discarded.
    assert phantoms, "expected page-break phantom line(s) to be detected"

    # No parsed item should have come from a phantom: phantoms carry a
    # truncated date like '2024-03-1' and '$0.00'. None of those leak through.
    assert all(i.total_amount_cents != 0 for i in items)
    assert all(i.date is not None and len(i.date) == 10 for i in items)


def test_phantom_detector_directly():
    phantom = OCRLine(
        tokens=[
            Token("continued", 0.38),
            Token("...", 0.30),
            Token("2024-03-1", 0.45),
            Token("$0.00", 0.42),
        ]
    )
    assert _looks_like_phantom(phantom) is True

    real = OCRLine(
        tokens=[
            Token("1", 0.97),
            Token("2024-03-10", 0.97),
            Token("Water", 0.97),
            Token("damage", 0.97),
            Token("Mitigation", 0.97),
            Token("1", 0.97),
            Token("$4,850.00", 0.97),
            Token("$4,850.00", 0.97),
        ]
    )
    assert _looks_like_phantom(real) is False


def test_hallucinated_token_dropped_without_shifting_columns():
    """Row 8 has an injected junk '~' token; money columns must stay aligned."""
    items, _ = _parse_synthetic()
    row8 = next(i for i in items if i.line_number == 8)
    assert "dropped_hallucinated_token" in row8.flags
    # Ground truth row 8: refrigerator, qty 1, $2199.00 unit & total.
    assert row8.total_amount_cents == 219900
    assert row8.unit_amount_cents == 219900


def test_description_and_category_extracted():
    items, _ = _parse_synthetic()
    row1 = next(i for i in items if i.line_number == 1)
    assert "Water damage" in (row1.description or "")
    assert row1.category == "Mitigation"
    assert row1.date == "2024-03-10"
