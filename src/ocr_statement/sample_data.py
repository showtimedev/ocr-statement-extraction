"""Synthetic Statement-of-Loss source data.

EVERYTHING HERE IS FAKE. No real claims, people, policies, or amounts. The data
is hand-authored so the pipeline's behavior is fully deterministic and so we can
deliberately seed the edge cases described in the README's "Known failure modes"
section (page-break phantom rows, digit transposition, OCR hallucinations).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceRow:
    """Ground-truth content of one statement line, before any OCR noise."""

    date: str
    description: str
    category: str
    quantity: float
    unit_amount_cents: int
    total_amount_cents: int


# Synthetic claimant / policy header (all fake).
STATEMENT_HEADER = {
    "title": "STATEMENT OF LOSS",
    "claim_number": "SYN-2024-000042",
    "policy_number": "POL-SYNTHETIC-7781",
    "insured_name": "Vandelay Industries (FICTITIOUS)",
    "date_of_loss": "2024-03-09",
    "prepared_by": "Synthetic Data Generator v0.1",
    "disclaimer": "SYNTHETIC SAMPLE - NO REAL DATA",
}

# Ground-truth line items. Two pages worth, so we can exercise page breaks.
SOURCE_ROWS: list[SourceRow] = [
    SourceRow("2024-03-10", "Water damage mitigation - main floor", "Mitigation", 1, 485000, 485000),
    SourceRow("2024-03-10", "Drywall removal and disposal", "Structural", 3, 62000, 186000),
    SourceRow("2024-03-11", "Hardwood flooring replacement", "Structural", 220, 1150, 253000),
    SourceRow("2024-03-11", "Contents cleaning - electronics", "Contents", 12, 4500, 54000),
    SourceRow("2024-03-12", "Temporary lodging reimbursement", "ALE", 4, 18900, 75600),
    SourceRow("2024-03-12", "HVAC inspection and recertification", "Mechanical", 1, 39500, 39500),
    SourceRow("2024-03-13", "Kitchen cabinetry replacement", "Structural", 8, 27500, 220000),
    SourceRow("2024-03-13", "Appliance replacement - refrigerator", "Contents", 1, 219900, 219900),
    SourceRow("2024-03-14", "Mold remediation - basement", "Mitigation", 1, 312000, 312000),
    SourceRow("2024-03-14", "Electrical panel repair", "Mechanical", 2, 48750, 97500),
    SourceRow("2024-03-15", "Window glazing replacement", "Structural", 6, 14250, 85500),
    SourceRow("2024-03-15", "Document recovery services", "Contents", 1, 67800, 67800),
]

# Rows per page in the generated PDF. Tuned so a row straddles the page break,
# which is what produces the "phantom row" edge case downstream.
ROWS_PER_PAGE = 7


def total_cents() -> int:
    """Ground-truth grand total across all rows."""
    return sum(r.total_amount_cents for r in SOURCE_ROWS)
