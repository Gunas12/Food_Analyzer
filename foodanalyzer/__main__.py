"""Allows `python -m foodanalyzer analyze <path>`.

Delegates straight to src.cli.main — no logic is duplicated here.
"""

from __future__ import annotations

from src.cli import main

if __name__ == "__main__":
    main()