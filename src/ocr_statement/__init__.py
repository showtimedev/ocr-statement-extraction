"""OCR Statement-of-Loss extraction pipeline.

A sanitized, synthetic-data reference implementation of a document-intelligence
pipeline:

    PDF -> OCR -> parse line items -> validate against schema
        -> confidence-threshold router -> structured JSON (+ review queue)

Everything in this package runs on synthetic data only. See the README for the
explicit "no real data" statement and the known failure modes.
"""

from .models import (
    BoundingBox,
    Token,
    OCRLine,
    OCRResult,
    LineItem,
    ExtractionResult,
)

__all__ = [
    "BoundingBox",
    "Token",
    "OCRLine",
    "OCRResult",
    "LineItem",
    "ExtractionResult",
]

__version__ = "0.1.0"
