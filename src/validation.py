"""Input validation for filesystem-based entry points (the CLI).

`api.py` validates multipart uploads (bytes) itself, since FastAPI hands it
raw bytes directly. The CLI instead gets a file *path* from the user, so it
needs a different check: does the file exist, is it a real JPEG/PNG, is it
under the size limit? This module answers that, and nothing else — it does
not know about FastAPI, argparse, or any specific caller.
"""

from __future__ import annotations

from pathlib import Path

_ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png"}

# Magic bytes let us catch a mislabeled file (e.g. a .txt renamed to .png)
# instead of trusting the extension alone.
_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class ValidationError(Exception):
    """Raised for any invalid image input. Plain exception — no framework
    dependency, so both the CLI and (if it chooses to) the API can catch it
    and translate it into their own error format (exit code / HTTP status).
    """


def validate_image_path(path: str, *, max_size_mb: float) -> Path:
    """Validate a filesystem path and return it as a Path if valid.

    Raises ValidationError with a human-readable message on any failure —
    missing file, wrong extension, oversized file, or content that doesn't
    match a real JPEG/PNG header.
    """
    p = Path(path)

    if not p.is_file():
        raise ValidationError(f"file not found: {path}")

    if p.suffix.lower() not in _ALLOWED_SUFFIXES:
        raise ValidationError(
            f"unsupported file extension {p.suffix!r}; "
            f"allowed: {sorted(_ALLOWED_SUFFIXES)}"
        )

    size_mb = p.stat().st_size / (1024 * 1024)
    if size_mb > max_size_mb:
        raise ValidationError(
            f"file too large: {size_mb:.1f} MB (max {max_size_mb} MB)"
        )
    if size_mb == 0:
        raise ValidationError("file is empty")

    with p.open("rb") as fh:
        head = fh.read(16)
    if not (head.startswith(_JPEG_MAGIC) or head.startswith(_PNG_MAGIC)):
        raise ValidationError(
            "file content does not look like a JPEG or PNG (magic-byte check failed)"
        )

    return p