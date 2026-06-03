import pytest

from app.config import Settings, validate_production_settings


def test_guard_rejects_placeholder_secret():
    s = Settings(debug=False, secret_key="change-me-in-production", cors_origins="https://x.com")
    with pytest.raises(RuntimeError, match="placeholder"):
        validate_production_settings(s)


def test_guard_rejects_wildcard_cors_in_prod():
    s = Settings(debug=False, secret_key="real-secret", cors_origins="*")
    with pytest.raises(RuntimeError, match="CORS"):
        validate_production_settings(s)


def test_guard_allows_secure_prod():
    validate_production_settings(Settings(debug=False, secret_key="real-secret", cors_origins="https://x.com"))


def test_guard_skips_in_debug():
    validate_production_settings(Settings(debug=True, secret_key="change-me-in-production", cors_origins="*"))
