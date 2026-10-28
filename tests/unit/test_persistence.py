"""Unit tests for SQLite persistence, repositories, corruption recovery, and schema constraints."""

from pathlib import Path

from recoverx.domain.candidate import RecoveryCandidate
from recoverx.domain.device import DeviceIdentity
from recoverx.domain.enums import (
    CandidateStatus,
    DeviceTriageStatus,
    JobStatus,
    RecoverySourceMethod,
)
from recoverx.domain.session import RecoverySession, ScanJobRecord
from recoverx.infrastructure.persistence.db import DatabaseManager
from recoverx.infrastructure.persistence.repositories import (
    CandidateRepository,
    JobRepository,
    SessionRepository,
)


def _make_dummy_identity(disk_id: str = "0x12345678") -> DeviceIdentity:
    return DeviceIdentity(
        vendor="SanDisk",
        product="Ultra USB 3.0",
        serial="4C530001",
        capacity_bytes=64 * 1024 * 1024,
        logical_sector_size=512,
        physical_sector_size=512,
        disk_identifier=disk_id,
        sector0_hash="a" * 64,
    )


def test_database_manager_memory_and_migrations() -> None:
    """Test memory database initialization and migrations applied."""
    db = DatabaseManager(":memory:")
    cursor = db.connection.execute("SELECT version FROM schema_migrations;")
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == 1
    db.close()


def test_session_repository(tmp_path: Path) -> None:
    """Test full CRUD operations on SessionRepository."""
    db_path = tmp_path / "test_sessions.db"
    db = DatabaseManager(db_path)
    repo = SessionRepository(db.connection)

    identity = _make_dummy_identity()
    session = RecoverySession(
        session_id="sess_001",
        name="USB Recovery Session",
        created_at=1000.0,
        updated_at=1000.0,
        status="active",
        source_path="/dev/sdb",
        source_identity=identity,
        triage_status=DeviceTriageStatus.SUPPORTED_FILESYSTEM,
        triage_notes="Intact FAT32 detected",
        notes="Urgent recovery",
    )

    repo.save(session)
    fetched = repo.get("sess_001")
    assert fetched is not None
    assert fetched.session_id == "sess_001"
    assert fetched.name == "USB Recovery Session"
    assert fetched.source_identity.vendor == "SanDisk"
    assert fetched.triage_status == DeviceTriageStatus.SUPPORTED_FILESYSTEM

    all_sessions = repo.list_all()
    assert len(all_sessions) == 1
    assert all_sessions[0].session_id == "sess_001"

    deleted = repo.delete("sess_001")
    assert deleted is True
    assert repo.get("sess_001") is None
    db.close()


def test_job_repository(tmp_path: Path) -> None:
    """Test job lifecycle persistence in JobRepository."""
    db_path = tmp_path / "test_jobs.db"
    db = DatabaseManager(db_path)
    session_repo = SessionRepository(db.connection)
    job_repo = JobRepository(db.connection)

    # Need a session first due to foreign keys
    session = RecoverySession(
        session_id="sess_job_test",
        name="Job Test",
        created_at=1000.0,
        updated_at=1000.0,
        status="active",
        source_path="/dev/sdc",
        source_identity=_make_dummy_identity(),
        triage_status=DeviceTriageStatus.SUPPORTED_FILESYSTEM,
    )
    session_repo.save(session)

    job = ScanJobRecord(
        job_id="job_001",
        session_id="sess_job_test",
        job_type="scan",
        status=JobStatus.RUNNING,
        source_identifier="0x12345678",
        created_at=1000.0,
        started_at=1001.0,
    )
    job_repo.save(job)

    active_jobs = job_repo.get_active_jobs()
    assert len(active_jobs) == 1
    assert active_jobs[0].job_id == "job_001"

    job_repo.update_status("job_001", JobStatus.COMPLETED)
    updated = job_repo.get("job_001")
    assert updated is not None
    assert updated.status == JobStatus.COMPLETED
    assert updated.completed_at is not None
    assert len(job_repo.get_active_jobs()) == 0
    db.close()


def test_candidate_repository_and_no_content_stored(tmp_path: Path) -> None:
    """Test candidate batch persistence and verify NO raw file content is stored in SQLite."""
    db_path = tmp_path / "test_candidates.db"
    db = DatabaseManager(db_path)
    session_repo = SessionRepository(db.connection)
    cand_repo = CandidateRepository(db.connection)

    session = RecoverySession(
        session_id="sess_cand_test",
        name="Candidate Test",
        created_at=1000.0,
        updated_at=1000.0,
        status="active",
        source_path="/dev/sdd",
        source_identity=_make_dummy_identity(),
        triage_status=DeviceTriageStatus.SUPPORTED_FILESYSTEM,
    )
    session_repo.save(session)

    candidates = [
        RecoveryCandidate(
            candidate_id="cand_1",
            filename="photo.jpg",
            relative_path="DCIM/photo.jpg",
            extension=".jpg",
            size_bytes=10240,
            source_offset=4096,
            source_method=RecoverySourceMethod.METADATA,
            status=CandidateStatus.METADATA_RECOVERED,
            sha256_hash="b" * 64,
        ),
        RecoveryCandidate(
            candidate_id="cand_2",
            filename="document.pdf",
            relative_path="Docs/document.pdf",
            extension=".pdf",
            size_bytes=20480,
            source_offset=16384,
            source_method=RecoverySourceMethod.CARVED,
            status=CandidateStatus.PREVIEW_VALIDATED,
        ),
    ]

    cand_repo.save_batch("sess_cand_test", candidates)
    assert cand_repo.count_by_session("sess_cand_test") == 2

    retrieved = cand_repo.get_by_session("sess_cand_test")
    assert len(retrieved) == 2
    assert retrieved[0].filename == "photo.jpg"
    assert retrieved[1].status == CandidateStatus.PREVIEW_VALIDATED

    # Test update recovered path
    cand_repo.update_candidate_recovered("cand_1", "/recovered/photo.jpg", "b" * 64)
    # Re-query DB to check updated recovered_path
    cursor = db.connection.execute(
        "SELECT recovered_path, sha256_hash FROM candidates WHERE candidate_id = 'cand_1';"
    )
    row = cursor.fetchone()
    assert row[0] == "/recovered/photo.jpg"
    assert row[1] == "b" * 64

    # FORENSIC CONSTRAINT ACCEPTANCE CHECK: Verify no table contains BLOB columns for file content
    cursor = db.connection.execute("PRAGMA table_info(candidates);")
    columns = [col[1] for col in cursor.fetchall()]
    assert "content" not in columns
    assert "data" not in columns
    assert "raw_bytes" not in columns

    db.close()


def test_corruption_recovery_path(tmp_path: Path) -> None:
    """Acceptance check: a corrupt database produces a clear recovery path (backup and rebuild)."""
    db_path = tmp_path / "corrupt_test.db"

    # Step 1: Create a valid database with a session
    db1 = DatabaseManager(db_path)
    session_repo1 = SessionRepository(db1.connection)
    session_repo1.save(
        RecoverySession(
            session_id="sess_before_corruption",
            name="Session Prior",
            created_at=1000.0,
            updated_at=1000.0,
            status="active",
            source_path="/dev/sde",
            source_identity=_make_dummy_identity(),
            triage_status=DeviceTriageStatus.SUPPORTED_FILESYSTEM,
        )
    )
    db1.close()

    # Step 2: Corrupt the database by overwriting it with garbage bytes
    with open(db_path, "wb") as f:
        f.write(b"NOT A VALID SQLITE DATABASE FILE - CORRUPTED HEADER AND B-TREE")

    # Step 3: Re-instantiate DatabaseManager
    # It must detect corruption, back up the corrupt database, and rebuild a fresh database
    db2 = DatabaseManager(db_path)

    # Check that a backup file was created matching the pattern corrupt_test.db.corrupt.*
    corrupt_backups = list(tmp_path.glob("corrupt_test.db.corrupt.*"))
    assert len(corrupt_backups) >= 1
    assert corrupt_backups[0].read_bytes().startswith(b"NOT A VALID SQLITE")

    # The new database connection must be clean and functional
    cursor = db2.connection.execute("PRAGMA integrity_check;")
    assert cursor.fetchone()[0] == "ok"

    session_repo2 = SessionRepository(db2.connection)
    assert len(session_repo2.list_all()) == 0  # Rebuilt clean, unblocked
    db2.close()
