"""Unit tests for RecoveryDestinationWriter atomic staging and cleanup guarantees."""

import hashlib
from pathlib import Path

from recoverx.domain.candidate import RecoveryCandidate
from recoverx.domain.enums import CandidateStatus, RecoverySourceMethod
from recoverx.infrastructure.storage.base import DeviceDisconnectedError
from recoverx.services.destination_writer import RecoveryDestinationWriter


def _make_candidate(content: bytes) -> tuple[RecoveryCandidate, bytes]:
    sha = hashlib.sha256(content).hexdigest()
    cand = RecoveryCandidate(
        candidate_id="cand-001",
        filename="test.bin",
        relative_path="test.bin",
        extension="bin",
        size_bytes=len(content),
        source_offset=0,
        source_method=RecoverySourceMethod.CARVED,
        status=CandidateStatus.PREVIEW_VALIDATED,
        sha256_hash=sha,
    )
    return cand, content


def test_successful_atomic_write(tmp_path: Path) -> None:
    content = b"FORENSIC_RECOVERY_PAYLOAD" * 100
    candidate, _ = _make_candidate(content)
    target_path = tmp_path / "recovered.bin"

    writer = RecoveryDestinationWriter(chunk_size_bytes=64)
    result = writer.write_candidate(
        candidate=candidate,
        final_destination_path=target_path,
        read_chunk_fn=lambda off, length: content[off : off + length],
    )

    assert result.is_successful
    assert result.bytes_written == len(content)
    assert result.hash_verified
    assert target_path.exists()
    assert target_path.read_bytes() == content

    # Verify no .part temporary staging files remain in directory
    part_files = list(tmp_path.glob("*.part"))
    assert len(part_files) == 0


def test_hash_mismatch_cleans_up_file(tmp_path: Path) -> None:
    content = b"EXPECTED_CONTENT"
    candidate, _ = _make_candidate(content)
    target_path = tmp_path / "corrupt.bin"

    # Source supplies altered bytes instead of expected content
    bad_source = b"TAMPERED_BYTES!!"
    writer = RecoveryDestinationWriter()
    result = writer.write_candidate(
        candidate=candidate,
        final_destination_path=target_path,
        read_chunk_fn=lambda off, length: bad_source[off : off + length],
    )

    assert not result.is_successful
    assert not result.hash_verified
    # File must NOT exist in destination!
    assert not target_path.exists()
    assert len(list(tmp_path.glob("*.part"))) == 0


def test_disk_full_simulation_leaves_no_partial_file(tmp_path: Path) -> None:
    content = b"LARGE_DATA_STREAM" * 500
    candidate, _ = _make_candidate(content)
    target_path = tmp_path / "disk_full.bin"

    # Simulate OSError: [Errno 28] No space left on device after 100 bytes
    call_count = 0

    def faulty_read(off: int, length: int) -> bytes:
        nonlocal call_count
        call_count += 1
        if call_count > 2:
            raise OSError(28, "No space left on device")
        return content[off : off + length]

    writer = RecoveryDestinationWriter(chunk_size_bytes=64)
    result = writer.write_candidate(
        candidate=candidate,
        final_destination_path=target_path,
        read_chunk_fn=faulty_read,
    )

    assert not result.is_successful
    assert "No space left on device" in (result.error_message or "")
    # Neither finalized file nor partial staging file may exist
    assert not target_path.exists()
    assert len(list(tmp_path.glob("*.part"))) == 0


def test_source_disconnect_leaves_no_partial_file(tmp_path: Path) -> None:
    content = b"DATA_BEFORE_DISCONNECT" * 50
    candidate, _ = _make_candidate(content)
    target_path = tmp_path / "unplugged.bin"

    def disconnected_read(off: int, length: int) -> bytes:
        raise DeviceDisconnectedError("Device suddenly unplugged")

    writer = RecoveryDestinationWriter()
    result = writer.write_candidate(
        candidate=candidate,
        final_destination_path=target_path,
        read_chunk_fn=disconnected_read,
    )

    assert not result.is_successful
    assert not target_path.exists()
    assert len(list(tmp_path.glob("*.part"))) == 0


def test_permission_denied_simulation_leaves_no_partial_file(tmp_path: Path) -> None:
    content = b"DATA_BEFORE_PERMISSION_ERROR" * 50
    candidate, _ = _make_candidate(content)
    target_path = tmp_path / "denied.bin"

    call_count = 0

    def permission_denied_read(off: int, length: int) -> bytes:
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise PermissionError("Access is denied")
        return content[off : off + length]

    writer = RecoveryDestinationWriter(chunk_size_bytes=64)
    result = writer.write_candidate(
        candidate=candidate,
        final_destination_path=target_path,
        read_chunk_fn=permission_denied_read,
    )

    assert not result.is_successful
    assert "Access is denied" in (result.error_message or "")
    assert not target_path.exists()
    assert len(list(tmp_path.glob("*.part"))) == 0
