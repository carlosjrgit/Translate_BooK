"""Permite a execução do pacote via python -m book_translator."""

from __future__ import annotations

import sys

from book_translator.cli import main

if __name__ == "__main__":
    sys.exit(main())
