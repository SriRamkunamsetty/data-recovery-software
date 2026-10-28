"""Unit tests for CLI and cross-platform imports."""

import sys
from unittest.mock import patch

import pytest

from recoverx._version import __version__
from recoverx.cli import main


def test_cli_version_flag() -> None:
    with patch.object(sys, "argv", ["recoverx", "--version"]):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0


def test_package_imports_cleanly_on_all_os() -> None:
    """Ensure core package imports without relying on Windows-specific libraries."""
    import recoverx
    import recoverx.config
    import recoverx.domain
    import recoverx.logging

    assert recoverx.__version__ == __version__
    assert recoverx.domain.CandidateStatus.METADATA_RECOVERED.value == "Metadata recovered"
