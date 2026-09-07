"""Unit tests for src/config.py — offline, isolated from the real .env file."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.config import Settings, get_settings


def test_defaults_are_sane():
    s = Settings(_env_file=None)
    assert s.llm_provider == "gemini"
    assert s.log_level == "INFO"
    assert s.http_port == 8000
    assert s.max_parallel == 10


def test_invalid_llm_provider_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_provider="chatgpt-turbo-9000")


def test_api_key_is_hidden_in_repr():
    s = Settings(_env_file=None, anthropic_api_key="sk-ant-super-secret")
    assert "sk-ant-super-secret" not in repr(s)
    assert s.anthropic_api_key.get_secret_value() == "sk-ant-super-secret"


def test_database_url_assembled_from_real_env_vars(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "appuser")
    monkeypatch.setenv("POSTGRES_PASSWORD", "s3cret")
    monkeypatch.setenv("POSTGRES_HOST", "db")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("POSTGRES_DB", "foodanalyzer")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    s = Settings(_env_file=None)
    assert s.database_url == "postgresql+asyncpg://appuser:s3cret@db:5433/foodanalyzer"


def test_explicit_database_url_wins_over_parts(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    s = Settings(_env_file=None)
    assert s.database_url == "sqlite+aiosqlite:///:memory:"


def test_port_out_of_range_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, http_port=99999)


def test_env_var_override_via_monkeypatch(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("MAX_PARALLEL", "3")
    get_settings.cache_clear()
    try:
        s = Settings()
        assert s.log_level == "DEBUG"
        assert s.max_parallel == 3
    finally:
        get_settings.cache_clear()

def test_max_image_size_bytes_property():
    s = Settings(_env_file=None, max_image_size_mb=2)
    assert s.max_image_size_bytes == 2 * 1024 * 1024


def test_get_settings_returns_a_settings_instance():
    get_settings.cache_clear()
    try:
        s = get_settings()
        assert isinstance(s, Settings)
    finally:
        get_settings.cache_clear()


def test_get_settings_is_cached_singleton():
    get_settings.cache_clear()
    try:
        first = get_settings()
        second = get_settings()
        assert first is second   
    finally:
        get_settings.cache_clear()