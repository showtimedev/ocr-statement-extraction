#!/usr/bin/env python3
"""Convenience entry point so the pipeline runs from the repo root.

    python run.py                       # generate sample PDF + extract
    python run.py path/to/statement.pdf --threshold 0.9 --out output

Equivalent to `python -m ocr_statement.cli` with src/ on the path.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from ocr_statement.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
