"""Core data models shared across the pipeline.

These are intentionally plain dataclasses (no pydantic) so the repo has a small
dependency surface and the data flow stays obvious to a reader.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass(frozen=True)
class BoundingBox:
    """Pixel/point coordinates of a token on a page (top-left origin)."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


@dataclass
class Token:
    """A single OCR token with its own confidence.

    `confidence` is a 0.0-1.0 score reported by the OCR engine for this token.
    Real engines (Tesseract) report 0-100 per word; we normalize to 0-1 at the
    adapter boundary so the rest of the pipeline only ever sees 0-1.
    """

    text: str
    confidence: float
    bbox: Optional[BoundingBox] = None
    page: int = 0


@dataclass
class OCRLine:
    """A horizontal line of tokens, as grouped by the OCR engine."""

    tokens: list[Token] = field(default_factory=list)
    page: int = 0

    @property
    def text(self) -> str:
        return " ".join(t.text for t in self.tokens)

    @property
    def confidence(self) -> float:
        """Mean token confidence for the line (1.0 for an empty line)."""
        if not self.tokens:
            return 1.0
        return sum(t.confidence for t in self.tokens) / len(self.tokens)


@dataclass
class OCRResult:
    """The full OCR output for a document."""

    lines: list[OCRLine] = field(default_factory=list)
    page_count: int = 1

    def lines_for_page(self, page: int) -> list[OCRLine]:
        return [ln for ln in self.lines if ln.page == page]


@dataclass
class LineItem:
    """A parsed Statement-of-Loss row.

    Monetary amounts are stored as integer cents to avoid float rounding error
    in financial data. `confidence` is the aggregate row confidence produced by
    the confidence scorer (see scoring.py).
    """

    line_number: int
    date: Optional[str]            # ISO 8601 date string, e.g. "2024-03-14"
    description: Optional[str]
    category: Optional[str]
    quantity: Optional[float]
    unit_amount_cents: Optional[int]
    total_amount_cents: Optional[int]

    confidence: float = 0.0
    source_page: int = 0
    raw_text: str = ""
    # Per-field confidences, used by the scorer and surfaced for reviewers.
    field_confidences: dict[str, float] = field(default_factory=dict)
    # Non-fatal issues found during parsing/scoring (e.g. "arithmetic_mismatch").
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExtractionResult:
    """Top-level pipeline output."""

    source_document: str
    is_synthetic: bool
    page_count: int
    confidence_threshold: float
    accepted: list[LineItem] = field(default_factory=list)
    review_queue: list[LineItem] = field(default_factory=list)
    # Rows that failed hard schema validation regardless of confidence.
    rejected: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_document": self.source_document,
            "is_synthetic": self.is_synthetic,
            "page_count": self.page_count,
            "confidence_threshold": self.confidence_threshold,
            "summary": {
                "accepted": len(self.accepted),
                "review_queue": len(self.review_queue),
                "rejected": len(self.rejected),
            },
            "accepted": [li.to_dict() for li in self.accepted],
            "review_queue": [li.to_dict() for li in self.review_queue],
            "rejected": self.rejected,
        }
