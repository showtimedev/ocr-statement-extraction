"""Generate the synthetic Statement-of-Loss PDF.

Uses reportlab to lay out a multi-page statement from the ground-truth rows in
sample_data.py. The layout (which row lands on which page, column x-positions)
is deliberately fixed so the deterministic OCR engine can mirror it.

Run:
    python -m ocr_statement.generate_pdf            # writes data/samples/statement_of_loss_synthetic.pdf
    python -m ocr_statement.generate_pdf out.pdf
"""

from __future__ import annotations

import os
import sys

from .sample_data import ROWS_PER_PAGE, SOURCE_ROWS, STATEMENT_HEADER, total_cents

DEFAULT_OUTPUT = os.path.join("data", "samples", "statement_of_loss_synthetic.pdf")


def _fmt_money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def _fmt_qty(qty: float) -> str:
    return f"{qty:g}"


def generate(output_path: str = DEFAULT_OUTPUT) -> str:
    """Render the synthetic PDF to `output_path`. Returns the path written."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except ImportError as exc:  # pragma: no cover - exercised only without reportlab
        raise RuntimeError(
            "reportlab is required to generate the PDF. Install with "
            "`pip install -r requirements.txt`."
        ) from exc

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    width, height = letter
    c = canvas.Canvas(output_path, pagesize=letter)

    # Column x-positions (points from left). Kept in sync conceptually with the
    # synthetic OCR engine, though the OCR engine works from SOURCE_ROWS directly.
    col_x = {
        "line": 50,
        "date": 90,
        "description": 170,
        "category": 360,
        "qty": 445,
        "unit": 480,
        "total": 545,
    }

    pages = [SOURCE_ROWS[i:i + ROWS_PER_PAGE] for i in range(0, len(SOURCE_ROWS), ROWS_PER_PAGE)]
    page_count = len(pages)
    line_counter = 0

    for page_index, page_rows in enumerate(pages):
        _draw_header(c, width, height, page_index, page_count)
        _draw_column_titles(c, height, col_x)

        y = height - 175
        for row in page_rows:
            line_counter += 1
            c.setFont("Helvetica", 9)
            c.drawString(col_x["line"], y, str(line_counter))
            c.drawString(col_x["date"], y, row.date)
            c.drawString(col_x["description"], y, row.description)
            c.drawString(col_x["category"], y, row.category)
            c.drawRightString(col_x["qty"] + 10, y, _fmt_qty(row.quantity))
            c.drawRightString(col_x["unit"] + 50, y, _fmt_money(row.unit_amount_cents))
            c.drawRightString(col_x["total"] + 25, y, _fmt_money(row.total_amount_cents))
            y -= 22

        # Grand total only on the final page.
        if page_index == page_count - 1:
            y -= 10
            c.setFont("Helvetica-Bold", 10)
            c.drawString(col_x["category"], y, "GRAND TOTAL")
            c.drawRightString(col_x["total"] + 25, y, _fmt_money(total_cents()))

        _draw_footer(c, width, page_index, page_count)
        c.showPage()

    c.save()
    return output_path


def _draw_header(c, width, height, page_index: int, page_count: int) -> None:
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, height - 50, STATEMENT_HEADER["title"])

    c.setFont("Helvetica-Bold", 8)
    c.setFillColorRGB(0.7, 0.1, 0.1)
    c.drawCentredString(width / 2, height - 64, STATEMENT_HEADER["disclaimer"])
    c.setFillColorRGB(0, 0, 0)

    c.setFont("Helvetica", 9)
    left = 50
    c.drawString(left, height - 90, f"Claim No: {STATEMENT_HEADER['claim_number']}")
    c.drawString(left, height - 103, f"Policy No: {STATEMENT_HEADER['policy_number']}")
    c.drawString(left, height - 116, f"Insured: {STATEMENT_HEADER['insured_name']}")
    c.drawString(360, height - 90, f"Date of Loss: {STATEMENT_HEADER['date_of_loss']}")
    c.drawString(360, height - 103, f"Page {page_index + 1} of {page_count}")


def _draw_column_titles(c, height, col_x) -> None:
    c.setFont("Helvetica-Bold", 8)
    y = height - 150
    c.drawString(col_x["line"], y, "#")
    c.drawString(col_x["date"], y, "DATE")
    c.drawString(col_x["description"], y, "DESCRIPTION")
    c.drawString(col_x["category"], y, "CATEGORY")
    c.drawString(col_x["qty"] - 10, y, "QTY")
    c.drawString(col_x["unit"] + 20, y, "UNIT")
    c.drawString(col_x["total"], y, "TOTAL")
    c.line(col_x["line"], y - 4, 570, y - 4)


def _draw_footer(c, width, page_index: int, page_count: int) -> None:
    c.setFont("Helvetica-Oblique", 7)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.drawCentredString(
        width / 2,
        30,
        "Synthetic document for pipeline testing - contains no real claim data.",
    )
    c.setFillColorRGB(0, 0, 0)


def main(argv: list[str]) -> int:
    out = argv[1] if len(argv) > 1 else DEFAULT_OUTPUT
    path = generate(out)
    print(f"Wrote synthetic Statement-of-Loss PDF: {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv))
