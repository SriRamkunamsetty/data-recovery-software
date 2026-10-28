"""SQLite database manager with WAL mode, integrity checks, and corruption recovery."""

import contextlib
import logging
import shutil
import sqlite3
import time
from pathlib import Path

from recoverx.domain.session import DatabaseCorruptionError
from recoverx.infrastructure.persistence.schema import MIGRATION_V1

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages SQLite connection lifecycle, integrity checks, and schema migrations.

    Ensures WAL mode and foreign key constraints are active.
    If database corruption is detected, automatically preserves a backup of the corrupted file
    and initializes a clean database to prevent blocking operations (Rule 15 of MASTER_PROMPT.md).
    """

    def __init__(self, db_path: Path | str = ":memory:") -> None:
        self.db_path = Path(db_path) if db_path != ":memory:" else None
        self._is_memory = db_path == ":memory:"
        self._connection: sqlite3.Connection | None = None
        self._initialize()

    def _initialize(self) -> None:
        """Connect to database, run integrity check, and apply pending migrations."""
        if not self._is_memory and self.db_path is not None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            if self.db_path.exists() and not self._check_integrity():
                self._recover_from_corruption()

        conn = self._create_connection()
        try:
            self._apply_migrations(conn)
        except Exception as exc:
            conn.close()
            if not self._is_memory and self.db_path is not None:
                logger.error("Migration failed (%s). Rebuilding database...", exc)
                self._recover_from_corruption()
                conn = self._create_connection()
                self._apply_migrations(conn)
            else:
                raise DatabaseCorruptionError(f"Failed to initialize database: {exc}") from exc

        self._connection = conn

    def _create_connection(self) -> sqlite3.Connection:
        target = ":memory:" if self._is_memory or self.db_path is None else str(self.db_path)
        conn = sqlite3.connect(target, check_same_thread=False)
        conn.row_factory = sqlite3.Row

        # Performance and safety pragmas
        conn.execute("PRAGMA foreign_keys = ON;")
        if not self._is_memory:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        return conn

    def _check_integrity(self) -> bool:
        """Run PRAGMA integrity_check to verify database file health."""
        if self._is_memory or self.db_path is None:
            return True

        try:
            test_conn = sqlite3.connect(str(self.db_path))
            try:
                cursor = test_conn.execute("PRAGMA integrity_check;")
                rows = cursor.fetchall()
                if rows and rows[0][0] == "ok":
                    return True
                logger.warning("Integrity check failed: %s", rows)
                return False
            finally:
                test_conn.close()
        except Exception as exc:
            logger.warning("Database integrity probe failed: %s", exc)
            return False

    def _recover_from_corruption(self) -> Path | None:
        """Back up corrupt database and clean up so a fresh database can be initialized."""
        if self._is_memory or self.db_path is None or not self.db_path.exists():
            return None

        timestamp = int(time.time())
        backup_path = self.db_path.with_name(f"{self.db_path.name}.corrupt.{timestamp}")
        logger.warning(
            "Database corruption detected. Backing up %s to %s and rebuilding clean schema.",
            self.db_path,
            backup_path,
        )

        try:
            shutil.copy2(self.db_path, backup_path)
        except OSError as exc:
            logger.error("Failed to copy corrupt db to backup: %s", exc)

        # Remove corrupt database and any SQLite sidecars (-wal, -shm)
        for p in (
            self.db_path,
            self.db_path.with_name(f"{self.db_path.name}-wal"),
            self.db_path.with_name(f"{self.db_path.name}-shm"),
        ):
            try:
                if p.exists():
                    p.unlink()
            except OSError:
                pass

        return backup_path

    def _apply_migrations(self, conn: sqlite3.Connection) -> None:
        """Apply pending migrations up to LATEST_SCHEMA_VERSION."""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at REAL NOT NULL
            );
            """
        )
        conn.commit()

        cursor = conn.execute("SELECT MAX(version) FROM schema_migrations;")
        row = cursor.fetchone()
        current_version = row[0] if (row and row[0] is not None) else 0

        if current_version < 1:
            conn.executescript(MIGRATION_V1)
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (1, ?);",
                (time.time(),),
            )
            conn.commit()

        # If future migrations (v2, v3) are added, apply sequentially here.

    @property
    def connection(self) -> sqlite3.Connection:
        """Active SQLite connection."""
        if self._connection is None:
            self._connection = self._create_connection()
        return self._connection

    def close(self) -> None:
        """Close database connection."""
        if self._connection is not None:
            with contextlib.suppress(Exception):
                self._connection.close()
            self._connection = None
