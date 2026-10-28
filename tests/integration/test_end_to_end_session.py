"""End-to-end integration test running session creation, coordinator, carving, and recovery."""

import hashlib
from pathlib import Path

from recoverx.config import CollisionPolicy
from recoverx.domain.enums import CandidateStatus, FileSystemType
from recoverx.infrastructure.persistence.db import DatabaseManager
from recoverx.infrastructure.storage.fixtures import ImageHashSnapshot
from recoverx.infrastructure.storage.image import DiskImageReader
from recoverx.infrastructure.storage.resolver import FakeVolumeIdentityResolver
from recoverx.services.report_service import ForensicReportData, ReportService
from recoverx.services.session_service import SessionService
from tests.fixtures.fat_builder import SyntheticFatBuilder


def test_end_to_end_session_recovery_workflow(tmp_path: Path) -> None:
    """Acceptance test: run full pipeline end-to-end on synthetic image with expected hashes."""
    # 1. Create a synthetic FAT32 image with known files
    src_img = tmp_path / "source_usb.img"
    builder = SyntheticFatBuilder(fs_type=FileSystemType.FAT32, volume_label="USB_SOURCE")

    valid_jpeg = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00"
        + b"\x01" * 64
        + b"\xff\xc0\x00\x0b\x08\x00\x08\x00\x08\x01\x01\x11\x00"
        + b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf"
        + b"\xff\xd9"
    )
    jpeg_hash = hashlib.sha256(valid_jpeg).hexdigest()

    doc_text = b"Confidential business recovery document text payload.\n" * 10
    doc_hash = hashlib.sha256(doc_text).hexdigest()

    builder.add_file(filename="PHOTO.JPG", content=valid_jpeg, is_deleted=True)
    builder.add_file(filename="DOC.TXT", content=doc_text, is_deleted=True)
    builder.build(src_img)

    # Record initial hash snapshot of the source device (Rule 1 of CLAUDE.md)
    snapshot = ImageHashSnapshot(src_img)

    # 2. Setup SQLite database, resolver, and SessionService
    db_path = tmp_path / "sessions.db"
    db_manager = DatabaseManager(db_path)

    resolver = FakeVolumeIdentityResolver()
    dest_dir = tmp_path / "recovered_output"
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Register distinct volumes to satisfy source/destination separation
    resolver.register_path_volume(dest_dir, "DEST_VOL", 2)

    session_service = SessionService(db_manager=db_manager, resolver=resolver)

    with DiskImageReader(src_img) as reader:
        resolver.register_device_volume(reader, "SRC_VOL", 1)

        # 3. Create Session
        session = session_service.create_session(
            source_path=str(src_img),
            source_device=reader,
            name="SD Card Recovery",
        )
        assert session.session_id.startswith("sess_")
        assert session_service.get_session(session.session_id) is not None

        # 4. Run Scan with Carving enabled
        scan_result = session_service.run_scan(
            session_id=session.session_id,
            device=reader,
            enable_carving=True,
        )

        assert scan_result.carving_executed is True
        assert len(scan_result.candidates) >= 2

        # Verify both deleted files were discovered
        photo_cand = next((c for c in scan_result.candidates if "PHOTO" in c.filename), None)
        doc_cand = next((c for c in scan_result.candidates if "DOC" in c.filename), None)

        assert photo_cand is not None
        assert doc_cand is not None

        # Verify candidate status
        assert photo_cand.status in (
            CandidateStatus.PREVIEW_VALIDATED,
            CandidateStatus.METADATA_RECOVERED,
        )
        assert doc_cand.status == CandidateStatus.METADATA_RECOVERED

        # 5. Recover Candidates to safe destination
        rec_results = session_service.recover_candidates(
            session_id=session.session_id,
            device=reader,
            candidate_ids=[photo_cand.candidate_id, doc_cand.candidate_id],
            destination_dir=dest_dir,
            collision_policy=CollisionPolicy.RENAME,
        )

        assert len(rec_results) == 2
        for r in rec_results:
            assert r.is_successful is True
            assert r.hash_verified is True

        # 6. Verify recovered files on disk match expected cryptographic hashes
        rec_photo = next(r for r in rec_results if r.candidate_id == photo_cand.candidate_id)
        rec_doc = next(r for r in rec_results if r.candidate_id == doc_cand.candidate_id)

        assert Path(rec_photo.destination_path).read_bytes() == valid_jpeg
        assert rec_photo.actual_sha256 == jpeg_hash

        assert Path(rec_doc.destination_path).read_bytes() == doc_text
        assert rec_doc.actual_sha256 == doc_hash

        # 7. Generate Forensic Report
        report_service = ReportService()
        report_data = ForensicReportData(
            report_id="rep_test_01",
            session_id=session.session_id,
            generated_at=1700000000.0,
            source_identity=reader.identity,
            triage_result=scan_result.triage_result,
            partitions=scan_result.partitions,
            candidates=scan_result.candidates,
            recovery_results=rec_results,
            scan_duration_seconds=scan_result.elapsed_seconds,
            carving_executed=scan_result.carving_executed,
        )

        json_out = tmp_path / "report.json"
        html_out = tmp_path / "report.html"
        report_service.export_json(report_data, json_out)
        report_service.export_html(report_data, html_out)

        assert json_out.exists()
        assert html_out.exists()

    # 8. Assert source storage device was 100% UNCHANGED (Rule 1 of CLAUDE.md)
    assert snapshot.verify_unchanged() is True
    db_manager.close()
