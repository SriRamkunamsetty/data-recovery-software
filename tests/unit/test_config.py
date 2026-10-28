"""Unit tests for configuration validation."""

import pytest

from recoverx.config import AppConfig, CollisionPolicy


def test_default_config_valid() -> None:
    config = AppConfig()
    assert config.scan_chunk_size_bytes == 1024 * 1024
    assert config.scan_overlap_bytes == 64 * 1024
    assert config.preview_timeout_seconds == 5.0
    assert config.collision_policy == CollisionPolicy.RENAME


def test_invalid_chunk_size_rejected() -> None:
    with pytest.raises(ValueError, match="scan_chunk_size_bytes must be positive"):
        AppConfig(scan_chunk_size_bytes=0)


def test_overlap_greater_than_chunk_rejected() -> None:
    with pytest.raises(ValueError, match="scan_overlap_bytes must be smaller"):
        AppConfig(scan_chunk_size_bytes=1000, scan_overlap_bytes=1000)
