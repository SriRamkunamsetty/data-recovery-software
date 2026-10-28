"""Pytest configuration and global fixtures."""

import pytest


@pytest.fixture
def sample_sha256() -> str:
    """A valid 64-character lowercase SHA-256 string for tests."""
    return "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
