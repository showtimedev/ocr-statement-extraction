"""Schema validation tests."""

from ocr_statement.models import LineItem
from ocr_statement.schema import is_valid, validate_line_item


def _valid_item(**overrides) -> LineItem:
    base = dict(
        line_number=1,
        date="2024-03-10",
        description="Water damage mitigation",
        category="Mitigation",
        quantity=1,
        unit_amount_cents=485000,
        total_amount_cents=485000,
    )
    base.update(overrides)
    return LineItem(**base)


def test_valid_item_passes():
    assert is_valid(_valid_item())


def test_missing_date_rejected():
    errors = validate_line_item(_valid_item(date=None))
    assert errors


def test_bad_date_format_rejected():
    errors = validate_line_item(_valid_item(date="03/10/2024"))
    assert any("date" in e for e in errors)


def test_negative_total_rejected():
    errors = validate_line_item(_valid_item(total_amount_cents=-5))
    assert any("total_amount_cents" in e for e in errors)


def test_unknown_category_rejected():
    errors = validate_line_item(_valid_item(category="Bogus"))
    assert any("category" in e for e in errors)


def test_null_category_allowed():
    assert is_valid(_valid_item(category=None))


def test_short_description_rejected():
    errors = validate_line_item(_valid_item(description="x"))
    assert any("description" in e for e in errors)
