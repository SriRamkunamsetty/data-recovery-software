"""Pytest configuration and global fixtures."""

import os

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Configure test environment for headless Qt UI testing."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def sample_sha256() -> str:
    """A valid 64-character lowercase SHA-256 string for tests."""
    return "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
