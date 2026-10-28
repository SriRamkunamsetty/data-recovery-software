"""Unit tests for structured logging."""

import io
import json
import logging

from recoverx.logging import StructuredJsonFormatter, get_logger, setup_logging


def test_structured_json_formatter() -> None:
    formatter = StructuredJsonFormatter()
    record = logging.LogRecord(
        name="recoverx.scanner",
        level=logging.INFO,
        pathname="scanner.py",
        lineno=42,
        msg="Found file signature",
        args=(),
        exc_info=None,
    )
    record.structured_data = {"signature": "JPEG", "offset": 1024}

    formatted_str = formatter.format(record)
    data = json.loads(formatted_str)

    assert data["level"] == "INFO"
    assert data["component"] == "recoverx.scanner"
    assert data["message"] == "Found file signature"
    assert data["data"]["signature"] == "JPEG"
    assert data["data"]["offset"] == 1024
    assert "timestamp" in data


def test_get_logger_attaches_context() -> None:
    stream = io.StringIO()
    setup_logging(level=logging.INFO, json_format=True, stream=stream)

    logger = get_logger("test_component", session_id="sess-99")
    logger.info("Scanning started", extra={"phase": "partition_scan"})

    output = stream.getvalue().strip()
    entry = json.loads(output)

    assert entry["component"] == "recoverx.test_component"
    assert entry["message"] == "Scanning started"
    assert entry["data"]["session_id"] == "sess-99"
    assert entry["data"]["phase"] == "partition_scan"
