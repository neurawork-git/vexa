import pytest


@pytest.fixture
def ms_env(monkeypatch):
    """Set required Microsoft env vars for tests that exercise configured paths."""
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "test-client-secret")


@pytest.fixture
def no_ms_env(monkeypatch):
    """Ensure Microsoft env vars are absent for not-configured guard tests."""
    monkeypatch.delenv("MICROSOFT_CLIENT_ID", raising=False)
    monkeypatch.delenv("MICROSOFT_CLIENT_SECRET", raising=False)
