"""Thin entrypoint package.

All real logic lives in `src/`. This package exists only so that
`python -m foodanalyzer analyze <path>` — the exact command the project
spec's "minimum runnable demo" checks for — works, without duplicating
`src/cli.py`.
"""