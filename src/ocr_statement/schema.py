"""JSON schema for a parsed Statement-of-Loss line item, plus validation.

Validation is intentionally separate from confidence scoring:

* Schema validation answers "is this row structurally usable at all?" A row that
  fails schema validation is *rejected* outright regardless of how confident the
  OCR was (e.g. missing a date, negative amount, non-ISO date).
* Confidence scoring (scoring.py) answers "should a human look at this?" A row
  can be perfectly valid yet still routed to review because a key field came
  back low-confidence.

This two-gate design is deliberate and is described in the README.
"""

from __future__ import annotations

from typing import Any

from .models import LineItem

# JSON Schema (draft 2020-12) for a single line item.
LINE_ITEM_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "StatementOfLossLineItem",
    "type": "object",
    "additionalProperties": True,
    "required": [
        "line_number",
        "date",
        "description",
        "total_amount_cents",
    ],
    "properties": {
        "line_number": {"type": "integer", "minimum": 1},
        "date": {
            "type": "string",
            "pattern": r"^\d{4}-\d{2}-\d{2}$",
        },
        "description": {"type": "string", "minLength": 3},
        "category": {
            "type": ["string", "null"],
            "enum": ["Mitigation", "Structural", "Contents", "ALE", "Mechanical", None],
        },
        "quantity": {"type": ["number", "null"], "exclusiveMinimum": 0},
        "unit_amount_cents": {"type": ["integer", "null"], "minimum": 0},
        "total_amount_cents": {"type": "integer", "minimum": 0},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "source_page": {"type": "integer", "minimum": 0},
    },
}


def validate_line_item(item: LineItem) -> list[str]:
    """Return a list of schema validation error messages (empty == valid).

    Uses jsonschema if available; otherwise falls back to a minimal built-in
    validator covering the required fields and key constraints so the pipeline
    still functions without the optional dependency.
    """
    payload = item.to_dict()
    try:
        import jsonschema

        validator = jsonschema.Draft202012Validator(LINE_ITEM_SCHEMA)
        return [
            f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}"
            for e in sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
        ]
    except ImportError:
        return _fallback_validate(payload)


def _fallback_validate(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    ln = payload.get("line_number")
    if not isinstance(ln, int) or ln < 1:
        errors.append("line_number: must be an integer >= 1")

    date = payload.get("date")
    if not isinstance(date, str):
        errors.append("date: required string")
    else:
        import re

        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
            errors.append("date: must match YYYY-MM-DD")

    desc = payload.get("description")
    if not isinstance(desc, str) or len(desc) < 3:
        errors.append("description: required string of length >= 3")

    total = payload.get("total_amount_cents")
    if not isinstance(total, int) or total < 0:
        errors.append("total_amount_cents: required non-negative integer")

    unit = payload.get("unit_amount_cents")
    if unit is not None and (not isinstance(unit, int) or unit < 0):
        errors.append("unit_amount_cents: must be a non-negative integer or null")

    qty = payload.get("quantity")
    if qty is not None and (not isinstance(qty, (int, float)) or qty <= 0):
        errors.append("quantity: must be a positive number or null")

    cat = payload.get("category")
    allowed = {"Mitigation", "Structural", "Contents", "ALE", "Mechanical", None}
    if cat not in allowed:
        errors.append(f"category: {cat!r} not in {sorted(c for c in allowed if c)}")

    return errors


def is_valid(item: LineItem) -> bool:
    return not validate_line_item(item)
