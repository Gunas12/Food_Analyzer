"""Offline tests for src/validation.py — uses tmp_path, no network/DB."""
from __future__ import annotations

import pytest

from src.validation import ValidationError, validate_image_path

_PNG_MAGIC = bytes.fromhex("89504e470d0a1a0a")
_JPEG_MAGIC = bytes.fromhex("ffd8ff")


def test_accepts_a_real_png(tmp_path):
    p = tmp_path / "meal.png"
    p.write_bytes(_PNG_MAGIC + b"\x00" * 20)
    result = validate_image_path(str(p), max_size_mb=5)
    assert result == p


def test_accepts_a_real_jpeg(tmp_path):
    p = tmp_path / "meal.jpg"
    p.write_bytes(_JPEG_MAGIC + b"\x00" * 20)
    validate_image_path(str(p), max_size_mb=5)


def test_rejects_missing_file(tmp_path):
    with pytest.raises(ValidationError, match="not found"):
        validate_image_path(str(tmp_path / "nope.png"), max_size_mb=5)


def test_rejects_wrong_extension(tmp_path):
    p = tmp_path / "meal.gif"
    p.write_bytes(_PNG_MAGIC + b"\x00" * 20)
    with pytest.raises(ValidationError, match="extension"):
        validate_image_path(str(p), max_size_mb=5)


def test_rejects_oversized_file(tmp_path):
    p = tmp_path / "meal.png"
    p.write_bytes(_PNG_MAGIC + b"\x00" * (6 * 1024 * 1024))
    with pytest.raises(ValidationError, match="too large"):
        validate_image_path(str(p), max_size_mb=5)


def test_rejects_empty_file(tmp_path):
    p = tmp_path / "meal.png"
    p.write_bytes(b"")
    with pytest.raises(ValidationError, match="empty"):
        validate_image_path(str(p), max_size_mb=5)


def test_rejects_mismatched_content(tmp_path):
    """.png extension but the bytes are plain text, not a real PNG."""
    p = tmp_path / "meal.png"
    p.write_text("this is not an image")
    with pytest.raises(ValidationError, match="magic-byte"):
        validate_image_path(str(p), max_size_mb=5)