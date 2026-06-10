"""OCR layer.

Two engines implement the same tiny interface (`run(pdf_path) -> OCRResult`):

* SyntheticOCREngine - deterministic, dependency-free. It renders the
  ground-truth rows into OCR tokens and *deliberately* injects the noise we want
  the downstream pipeline to cope with: per-token confidence drops, digit
  transposition, a hallucinated token, and a page-break "phantom" partial row.
  This is what the tests and the default CLI run use.

* TesseractOCREngine - optional real backend (pytesseract + pdf2image). Imported
  lazily so the package works without it. Normalizes Tesseract's 0-100 word
  confidence to 0-1 at this boundary.

Keeping both behind one interface is the point: the confidence router, schema
validation, and parsing never need to know which engine produced the tokens.
"""

from __future__ import annotations

from typing import Protocol

from .models import BoundingBox, OCRLine, OCRResult, Token
from .sample_data import ROWS_PER_PAGE, SOURCE_ROWS, STATEMENT_HEADER, total_cents


class OCREngine(Protocol):
    def run(self, pdf_path: str) -> OCRResult: ...


def _money_str(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def _qty_str(qty: float) -> str:
    return f"{qty:g}"


class SyntheticOCREngine:
    """Deterministic OCR that mirrors generate_pdf's layout and injects noise.

    The noise is seeded by row index so results are reproducible across runs,
    which keeps the tests stable while still exercising every failure mode.
    """

    # High baseline confidence; specific tokens get knocked down below.
    BASE_CONF = 0.97

    def run(self, pdf_path: str) -> OCRResult:  # noqa: ARG002 - path kept for interface parity
        lines: list[OCRLine] = []
        pages = [SOURCE_ROWS[i:i + ROWS_PER_PAGE] for i in range(0, len(SOURCE_ROWS), ROWS_PER_PAGE)]
        page_count = len(pages)
        line_counter = 0

        for page_index, page_rows in enumerate(pages):
            lines.extend(self._header_lines(page_index, page_count))

            for local_idx, row in enumerate(page_rows):
                line_counter += 1
                lines.append(self._row_line(line_counter, row, page_index))

            # --- Edge case: page-break phantom row ----------------------
            # When a page breaks, repeated column headers / footer fragments
            # from the next page sometimes get OCR'd as a partial data row.
            # We emit that here on every page except the last so the parser
            # has to defend against it.
            if page_index < page_count - 1:
                lines.append(self._phantom_partial_row(page_index))

            if page_index == page_count - 1:
                lines.append(self._grand_total_line(page_index))

        return OCRResult(lines=lines, page_count=page_count)

    # ------------------------------------------------------------------ #
    # Header / footer lines
    # ------------------------------------------------------------------ #
    def _header_lines(self, page_index: int, page_count: int) -> list[OCRLine]:
        def line(text: str, conf: float = self.BASE_CONF) -> OCRLine:
            toks = [Token(t, conf, page=page_index) for t in text.split()]
            return OCRLine(tokens=toks, page=page_index)

        out = [
            line(STATEMENT_HEADER["title"]),
            line(STATEMENT_HEADER["disclaimer"]),
            line(f"Claim No: {STATEMENT_HEADER['claim_number']}"),
            line(f"Policy No: {STATEMENT_HEADER['policy_number']}"),
            line(f"Page {page_index + 1} of {page_count}"),
            line("# DATE DESCRIPTION CATEGORY QTY UNIT TOTAL"),
        ]
        return out

    # ------------------------------------------------------------------ #
    # Data rows
    # ------------------------------------------------------------------ #
    def _row_line(self, line_number: int, row, page_index: int) -> OCRLine:
        tokens: list[Token] = []
        x = 50.0

        def add(text: str, conf: float = self.BASE_CONF) -> None:
            nonlocal x
            tokens.append(
                Token(text, conf, bbox=BoundingBox(x, 0, x + 8 * len(text), 10), page=page_index)
            )
            x += 8 * len(text) + 6

        add(str(line_number))
        add(row.date)
        for word in row.description.split():
            add(word)
        add(row.category)
        add(_qty_str(row.quantity))

        # --- Injected noise, seeded by line number for determinism -------
        unit_str = _money_str(row.unit_amount_cents)
        total_str = _money_str(row.total_amount_cents)

        # Failure mode 1: digit transposition in a money field.
        # Row 3 ("Hardwood flooring") gets its total digits swapped, which the
        # arithmetic check (qty * unit == total) should later catch.
        if line_number == 3:
            total_str = self._transpose_digits(total_str)
            add(unit_str)
            add(total_str, conf=0.74)  # OCR itself is a bit unsure here too
        # Failure mode 2: low-confidence money token (smudge / faint print).
        # Row 5 unit amount comes back low-confidence -> should route to review.
        elif line_number == 5:
            add(unit_str, conf=0.55)
            add(total_str, conf=0.55)
        # Failure mode 3: OCR hallucination - an extra spurious token mid-row.
        # Row 8 gets a junk token inserted; the parser must not let it shift the
        # money columns.
        elif line_number == 8:
            add("~", conf=0.41)
            add(unit_str)
            add(total_str)
        else:
            add(unit_str)
            add(total_str)

        return OCRLine(tokens=tokens, page=page_index)

    def _phantom_partial_row(self, page_index: int) -> OCRLine:
        """A garbled partial row produced at the page boundary.

        It has a date-shaped fragment and a stray amount but no real
        description/category -- exactly the kind of thing that, if naively
        parsed, becomes a phantom line item.
        """
        toks = [
            Token("continued", 0.38, page=page_index),
            Token("...", 0.30, page=page_index),
            Token("2024-03-1", 0.45, page=page_index),  # truncated date fragment
            Token("$0.00", 0.42, page=page_index),
        ]
        return OCRLine(tokens=toks, page=page_index)

    def _grand_total_line(self, page_index: int) -> OCRLine:
        text = f"GRAND TOTAL {_money_str(total_cents())}"
        toks = [Token(t, self.BASE_CONF, page=page_index) for t in text.split()]
        return OCRLine(tokens=toks, page=page_index)

    @staticmethod
    def _transpose_digits(money: str) -> str:
        """Swap two adjacent digits to simulate a transposition error.

        '$2,530.00' -> '$2,350.00'  (swaps the first adjacent digit pair found)
        """
        chars = list(money)
        digit_positions = [i for i, ch in enumerate(chars) if ch.isdigit()]
        for a, b in zip(digit_positions, digit_positions[1:]):
            if b == a + 1 and chars[a] != chars[b]:
                chars[a], chars[b] = chars[b], chars[a]
                break
        return "".join(chars)


class TesseractOCREngine:  # pragma: no cover - requires system deps
    """Optional real OCR backend. Lazily imports pytesseract + pdf2image.

    Normalizes Tesseract's 0-100 per-word confidence into the 0-1 range the rest
    of the pipeline expects. Words with confidence -1 (Tesseract's "no estimate")
    are dropped.
    """

    def __init__(self, dpi: int = 300):
        self.dpi = dpi

    def run(self, pdf_path: str) -> OCRResult:
        try:
            import pytesseract
            from pdf2image import convert_from_path
            from pytesseract import Output
        except ImportError as exc:
            raise RuntimeError(
                "TesseractOCREngine needs pytesseract + pdf2image (and the "
                "system `tesseract`/`poppler` binaries). See requirements.txt."
            ) from exc

        images = convert_from_path(pdf_path, dpi=self.dpi)
        lines: list[OCRLine] = []
        for page_index, image in enumerate(images):
            data = pytesseract.image_to_data(image, output_type=Output.DICT)
            grouped: dict[tuple, list[Token]] = {}
            for i, text in enumerate(data["text"]):
                if not text.strip():
                    continue
                conf_raw = float(data["conf"][i])
                if conf_raw < 0:
                    continue
                key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
                tok = Token(
                    text=text,
                    confidence=conf_raw / 100.0,
                    bbox=BoundingBox(
                        data["left"][i],
                        data["top"][i],
                        data["left"][i] + data["width"][i],
                        data["top"][i] + data["height"][i],
                    ),
                    page=page_index,
                )
                grouped.setdefault(key, []).append(tok)
            for toks in grouped.values():
                lines.append(OCRLine(tokens=toks, page=page_index))

        return OCRResult(lines=lines, page_count=len(images))


def get_default_engine() -> OCREngine:
    """The pipeline default: dependency-free synthetic engine."""
    return SyntheticOCREngine()
