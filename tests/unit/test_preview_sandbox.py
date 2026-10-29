"""Unit tests for sandboxed preview subprocess execution, limits, and safety."""

import io
import struct
import zipfile
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from recoverx.domain.candidate import RecoveryCandidate
from recoverx.domain.enums import CandidateStatus, RecoverySourceMethod
from recoverx.infrastructure.storage.image import DiskImageReader
from recoverx.presentation.demo import _create_minimal_jpeg
from recoverx.presentation.dialogs.preview_dialog import FilePreviewDialog
from recoverx.presentation.preview.sandbox import PreviewSandbox


@pytest.fixture
def sandbox() -> PreviewSandbox:
    return PreviewSandbox(default_timeout_sec=5.0)


def test_preview_sandbox_empty_input(sandbox: PreviewSandbox) -> None:
    """Test preview sandbox gracefully rejects 0-byte input."""
    res = sandbox.generate_preview(b"", "txt")
    assert res.success is False
    assert res.preview_type == "error"
    assert "Empty" in res.error


def test_preview_sandbox_text(sandbox: PreviewSandbox) -> None:
    """Test preview sandbox extracts and sanitizes text content."""
    text_data = b"Hello RecoverX Forensic Recovery!\nLine 2\tIndented"
    res = sandbox.generate_preview(text_data, "txt")
    assert res.success is True
    assert res.preview_type == "text"
    assert "Hello RecoverX" in res.content
    assert res.metadata.get("lines_count") == 2


def test_preview_sandbox_image_jpeg(sandbox: PreviewSandbox) -> None:
    """Test preview sandbox decodes JPEG and returns base64 PNG."""
    jpeg_data = _create_minimal_jpeg()
    res = sandbox.generate_preview(jpeg_data, "jpg")
    assert res.success is True
    assert res.preview_type == "image"
    assert res.metadata.get("width") == 1
    assert res.metadata.get("height") == 1
    assert len(res.image_b64) > 0


def test_preview_sandbox_audio_wav(sandbox: PreviewSandbox) -> None:
    """Test preview sandbox extracts WAV metadata without playback."""
    audio_data = b"\x00\x10" * 32
    fmt_chunk = struct.pack("<4sIHHIIHH", b"fmt ", 16, 1, 2, 44100, 44100 * 4, 4, 16)
    data_chunk = struct.pack("<4sI", b"data", len(audio_data)) + audio_data
    riff_payload = b"WAVE" + fmt_chunk + data_chunk
    wav_bytes = struct.pack("<4sI", b"RIFF", len(riff_payload)) + riff_payload

    res = sandbox.generate_preview(wav_bytes, "wav")
    assert res.success is True
    assert res.preview_type == "audio"
    assert "44,100" in res.metadata.get("sample_rate", "")
    assert "Stereo" in res.metadata.get("channels", "")


def test_preview_sandbox_sqlite(sandbox: PreviewSandbox) -> None:
    """Test preview sandbox extracts SQLite header metadata safely."""
    hdr = bytearray(100)
    hdr[:16] = b"SQLite format 3\x00"
    struct.pack_into(">H", hdr, 16, 4096)
    struct.pack_into(">I", hdr, 28, 12)  # 12 pages
    struct.pack_into(">I", hdr, 56, 1)  # UTF-8

    res = sandbox.generate_preview(bytes(hdr) + b"\x00" * 1000, "sqlite")
    assert res.success is True
    assert res.preview_type == "sqlite"
    assert res.metadata.get("page_size") == "4096 bytes"
    assert res.metadata.get("total_pages") == "12"


def test_preview_sandbox_zip_safe_and_slip_detection(sandbox: PreviewSandbox) -> None:
    """Test preview sandbox lists zip entries and flags zip-slip attempts."""
    # 1. Normal safe zip
    buf_safe = io.BytesIO()
    with zipfile.ZipFile(buf_safe, "w") as zf:
        zf.writestr("safe_doc.txt", "Hello World")
        zf.writestr("subfolder/data.csv", "1,2,3")

    res_safe = sandbox.generate_preview(buf_safe.getvalue(), "zip")
    assert res_safe.success is True
    assert res_safe.preview_type == "archive"
    assert res_safe.metadata.get("total_entries") == 2
    assert res_safe.metadata.get("zip_slip_risk") == "None"
    assert len(res_safe.entries) == 2

    # 2. Malicious zip with path traversal (Zip Slip)
    buf_slip = io.BytesIO()
    with zipfile.ZipFile(buf_slip, "w") as zf:
        zf.writestr("../../etc/shadow", "root:x:0:0")

    res_slip = sandbox.generate_preview(buf_slip.getvalue(), "zip")
    assert res_slip.success is True
    assert "DETECTED" in res_slip.metadata.get("zip_slip_risk", "")


def test_preview_sandbox_corrupt_data(sandbox: PreviewSandbox) -> None:
    """Test preview sandbox fails gracefully without unhandled exceptions on corrupt data."""
    garbage = b"\x00\xff\xaa\x55" * 128
    res = sandbox.generate_preview(garbage, "jpg")
    assert res.success is False
    assert res.preview_type == "error"
    assert "Failed to decode" in res.error


def test_file_preview_dialog_with_sandbox(qapp: QApplication, tmp_path: Path) -> None:
    """Test FilePreviewDialog correctly wires PreviewSandbox and renders without hanging."""
    text_content = b"Recovered Forensic Log Data\nStatus: OK"
    img_path = tmp_path / "test_preview_dialog.raw"
    img_path.write_bytes(text_content + b"\x00" * 512)

    cand = RecoveryCandidate(
        candidate_id="cand_test",
        filename="LOG.TXT",
        relative_path="LOG.TXT",
        extension=".txt",
        size_bytes=len(text_content),
        source_offset=0,
        source_method=RecoverySourceMethod.METADATA,
        status=CandidateStatus.METADATA_RECOVERED,
    )

    with DiskImageReader(img_path) as reader:
        dialog = FilePreviewDialog(candidate=cand, device=reader)
        assert dialog.accessibleName() == "File Preview Dialog"
        dialog.close()
