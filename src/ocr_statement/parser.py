"""Parse OCR lines into structured LineItem rows.

Responsibilities:
* Identify which OCR lines are actual data rows (vs. headers, footers, totals,
  and page-break phantom rows).
* Pull out date / description / category / quantity / unit / total.
* Be defensive about the injected noise: hallucinated tokens, truncated
  page-break fragments, and money tokens whose digits got mangled.

The parser does NOT decide accept/review/reject -- it only structures the data
and records per-field confidence + parse flags. Scoring and routing happen
later, so each concern stays testable in isolation.
"""

from __future__ import annotations

import re
from typing import Optional

from .models import LineItem, OCRLine, OCRResult, Token

# ---- Token recognizers -------------------------------------------------- #
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PARTIAL_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{1,2}$")  # phantom fragments
MONEY_RE = re.compile(r"^\$?\d{1,3}(,\d{3})*(\.\d{2})?$|^\$?\d+(\.\d{2})?$")
QTY_RE = re.compile(r"^\d+(\.\d+)?$")

# Lines whose text contains any of these are structural, not data rows.
NON_DATA_MARKERS = (
    "STATEMENT OF LOSS",
    "GRAND TOTAL",
    "DESCRIPTION",
    "Claim No",
    "Policy No",
    "Page ",
    "SYNTHETIC",
    "continued",
)

KNOWN_CATEGORIES = {
    "Mitigation",
    "Structural",
    "Contents",
    "ALE",
    "Mechanical",
}


def _money_to_cents(text: str) -> Optional[int]:
    cleaned = text.replace("$", "").replace(",", "")
    if not re.fullmatch(r"\d+(\.\d{1,2})?", cleaned):
        return None
    if "." in cleaned:
        dollars, frac = cleaned.split(".")
        frac = (frac + "00")[:2]
        return int(dollars) * 100 + int(frac)
    return int(cleaned) * 100


def _is_data_row(line: OCRLine) -> bool:
    """True if the line looks like a real statement line item."""
    text = line.text
    if any(marker in text for marker in NON_DATA_MARKERS):
        return False
    tokens = line.tokens
    if not tokens:
        return False

    # Must begin with an integer line number.
    if not tokens[0].text.isdigit():
        return False

    # Must contain a full date and at least one money-shaped token.
    has_full_date = any(DATE_RE.match(t.text) for t in tokens)
    has_money = any(t.text.startswith("$") for t in tokens)
    return has_full_date and has_money


def _looks_like_phantom(line: OCRLine) -> bool:
    """Page-break phantom rows: fragmentary, low-confidence, no real date."""
    text = line.text
    if "continued" in text or "..." in text:
        return True
    has_full_date = any(DATE_RE.match(t.text) for t in line.tokens)
    has_partial_date = any(
        PARTIAL_DATE_RE.match(t.text) and not DATE_RE.match(t.text) for t in line.tokens
    )
    # Partial-but-not-full date with very low line confidence is the signature.
    return has_partial_date and not has_full_date and line.confidence < 0.6


def parse(ocr: OCRResult) -> tuple[list[LineItem], list[OCRLine]]:
    """Parse an OCRResult.

    Returns (line_items, dropped_phantom_lines). Phantom lines are returned so
    the caller can log/inspect what was discarded at page boundaries.
    """
    items: list[LineItem] = []
    phantoms: list[OCRLine] = []

    for line in ocr.lines:
        if _looks_like_phantom(line):
            phantoms.append(line)
            continue
        if not _is_data_row(line):
            continue
        items.append(_parse_row(line))

    return items, phantoms


def _parse_row(line: OCRLine) -> LineItem:
    tokens = line.tokens
    flags: list[str] = []
    field_conf: dict[str, float] = {}

    # Drop obvious hallucination tokens (very low confidence non-word symbols)
    # before column assignment so they don't shift the money columns.
    cleaned: list[Token] = []
    for t in tokens:
        if t.confidence < 0.5 and not re.search(r"[A-Za-z0-9]", t.text):
            flags.append("dropped_hallucinated_token")
            continue
        cleaned.append(t)
    tokens = cleaned

    line_number = int(tokens[0].text)
    field_conf["line_number"] = tokens[0].confidence

    # Date: first full-date token.
    date_val: Optional[str] = None
    date_idx: Optional[int] = None
    for i, t in enumerate(tokens):
        if DATE_RE.match(t.text):
            date_val = t.text
            date_idx = i
            field_conf["date"] = t.confidence
            break

    # Money tokens: take the last two money-shaped tokens as unit, total.
    money_idx = [i for i, t in enumerate(tokens) if t.text.startswith("$")]
    unit_cents = total_cents_val = None
    if len(money_idx) >= 2:
        unit_tok = tokens[money_idx[-2]]
        total_tok = tokens[money_idx[-1]]
        unit_cents = _money_to_cents(unit_tok.text)
        total_cents_val = _money_to_cents(total_tok.text)
        field_conf["unit_amount_cents"] = unit_tok.confidence
        field_conf["total_amount_cents"] = total_tok.confidence
    elif len(money_idx) == 1:
        total_tok = tokens[money_idx[-1]]
        total_cents_val = _money_to_cents(total_tok.text)
        field_conf["total_amount_cents"] = total_tok.confidence
        flags.append("missing_unit_amount")

    # Quantity: a bare number sitting between the description and the money
    # columns (after the date, before the first money token).
    qty_val: Optional[float] = None
    first_money = money_idx[0] if money_idx else len(tokens)
    for i in range(first_money - 1, (date_idx or 0), -1):
        t = tokens[i]
        if QTY_RE.match(t.text) and not t.text.startswith("$"):
            qty_val = float(t.text)
            field_conf["quantity"] = t.confidence
            break

    # Category: known category word. Searched from the RIGHT, because the
    # category column sits to the right of the description and a category word
    # (e.g. "Contents") can also legitimately appear inside a description
    # ("Contents cleaning - electronics"). The rightmost match before the money
    # columns is the real category.
    category: Optional[str] = None
    cat_idx: Optional[int] = None
    for i in range(first_money - 1, -1, -1):
        t = tokens[i]
        if t.text in KNOWN_CATEGORIES:
            category = t.text
            cat_idx = i
            field_conf["category"] = t.confidence
            break

    # Description: tokens between the date and the category (or qty/money).
    desc_start = (date_idx + 1) if date_idx is not None else 1
    desc_end = cat_idx if cat_idx is not None else first_money
    desc_tokens = tokens[desc_start:desc_end]
    # Strip a trailing quantity token if it slipped into the description span.
    desc_tokens = [t for t in desc_tokens if not (QTY_RE.match(t.text) and t.text == (str(qty_val) if qty_val else None))]
    description = " ".join(t.text for t in desc_tokens) or None
    if desc_tokens:
        field_conf["description"] = sum(t.confidence for t in desc_tokens) / len(desc_tokens)

    return LineItem(
        line_number=line_number,
        date=date_val,
        description=description,
        category=category,
        quantity=qty_val,
        unit_amount_cents=unit_cents,
        total_amount_cents=total_cents_val,
        source_page=line.page,
        raw_text=line.text,
        field_confidences=field_conf,
        flags=flags,
    )
