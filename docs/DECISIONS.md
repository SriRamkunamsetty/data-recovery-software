# Architecture Decision Records (ADRs)

This document tracks all key technical, architectural, tooling, and dependency decisions made in the RecoverX project.

---

## ADR 001: Python Runtime Version Pinning

* **Status:** Accepted
* **Context:** RecoverX needs modern Python typing features, performance improvements in binary handling, and long-term stability across Windows and Linux test environments.
* **Decision:** Target Python 3.12 (specifically tested against CPython 3.12.13). We configure `requires-python = ">=3.12"` with strict testing under 3.12.
* **Rationale:** Python 3.12 introduces faster comprehension execution, improved error locations, native support for type parameter syntax (PEP 695), and broad, stable binary wheel availability for PySide6 and testing tooling.
* **Consequences:** Codebase can freely use Python 3.12 typing and standard library features while remaining strictly typed.

---

## ADR 002: Dependency Selection and Rationale

* **Status:** Accepted
* **Context:** CLAUDE.md and MASTER_PROMPT.md require every external dependency beyond standard library to have an explicit justification and verified license. RecoverX prioritizes safety, auditable code, and minimal attack surface.
* **Core Dependencies:**
  1. **`PySide6`**:
     * *Purpose:* Official Qt for Python bindings for the desktop GUI.
     * *License:* LGPLv3 / Commercial.
     * *Rationale:* PySide6 provides cross-platform desktop UI capabilities, high-DPI scaling, dark/light theme support, and native widget performance. To comply with LGPLv3, the application will be distributed in PyInstaller `onedir` mode with dynamic linking, allowing users to swap Qt libraries if desired.
  2. **`pytest`**:
     * *Purpose:* Test execution and test runner.
     * *License:* MIT.
     * *Rationale:* Industry standard Python test framework offering rich assertion reporting, fixture management, and modular test organization.
  3. **`pytest-qt`**:
     * *Purpose:* Qt fixture and headless testing helper for pytest.
     * *License:* MIT.
     * *Rationale:* Enables testing PySide6 signals, slots, and dialogs offscreen (`QT_QPA_PLATFORM=offscreen`) without requiring a live desktop display, ensuring continuous integration runs cleanly on headless CI.
  4. **`Hypothesis`**:
     * *Purpose:* Property-based testing framework.
     * *License:* MPLv2.
     * *Rationale:* Essential for testing binary parsers (MBR, GPT, FAT, exFAT, NTFS, file carvers) against malformed, adversarial, and truncated byte inputs to guarantee that parsers never crash or enter infinite loops.
  5. **`ruff`**:
     * *Purpose:* Fast linter and code formatter.
     * *License:* MIT / Apache-2.0.
     * *Rationale:* Replaces Flake8, Black, and isort with sub-second execution speeds, enforcing consistent code quality and formatting.
  6. **`mypy`**:
     * *Purpose:* Static type checker running in strict mode.
     * *License:* MIT.
     * *Rationale:* Enforces complete type safety across all domain models, services, and hardware abstractions, preventing runtime `None` dereferences, type confusion, or unhandled states.
  7. **`hatchling`**:
     * *Purpose:* Modern build backend conforming to PEP 517 / PEP 621.
     * *License:* MIT.
     * *Rationale:* Lightweight, standard-compliant build tool that builds clean wheels and editable packages (`uv pip install -e .`) without legacy setuptools bloat.
* **Dependencies Rejected or Deferred:**
  * *`pydantic`*: Rejected for domain models to avoid runtime overhead and serialization complexities; Python standard library `@dataclass(frozen=True)` with custom `__post_init__` checks provides zero-overhead, strictly typed data structures.
  * *`GPL recovery libraries (TestDisk, PhotoRec, ddrescue, Sleuth Kit)`*: Forbidden from being bundled or copied; all formats and algorithms are reimplemented independently from official specifications.

---

## ADR 003: Elevated Read Helper for Windows Raw Disk Access

* **Status:** Accepted (to be implemented in M10)
* **Context:** Accessing raw disk handles (`\\.\PhysicalDriveN`) requires elevated (Administrator) rights on Windows. Running the entire Qt GUI as Administrator creates severe security risks and drags untrusted recovered data into high integrity.
* **Decision:** The GUI process runs unelevated (standard user). When raw device access is required, a lightweight elevated helper process is spawned via UAC, communicating with the GUI over an authenticated Named Pipe with a strict user-only ACL.
* **Rationale:** A hung read on a damaged drive can be cancelled without freezing the GUI. The helper implements only a minimal, audited API: `open`, `read_at`, `get_metadata`, `close`, `cancel`.

---

## ADR 004: Factual Candidate Statuses (No Percentage Guarantees)

* **Status:** Accepted
* **Context:** Commercial data recovery software frequently misleads users with arbitrary percentage estimates (e.g., "95% chance of recovery") that have no mathematical or forensic basis.
* **Decision:** RecoverX strictly uses factual status enums:
  * `Metadata recovered`: Found through intact directory/filesystem tables.
  * `Signature matched`: File header signature detected, but internal structure is not yet verified.
  * `Preview validated`: Complete file structure successfully decoded by format validator or preview generator.
  * `Partially readable`: File contains unreadable sectors or bad blocks.
  * `Truncated`: File structure ends prematurely before the expected end marker.
  * `Unverified`: Recovered without formal validator check.
  * `Recovery failed`: Output could not be written or read failed completely.
* **Rationale:** Preserves forensic integrity and sets transparent user expectations.

---

## ADR 005: Project Licensing Placeholder

* **Status:** Pending Owner Selection
* **Context:** A formal software license must be chosen by the project repository owner prior to release.
* **Decision:** Marked as "Owner to decide" in `LICENSE`. Third-party notices and LGPL compliance requirements are documented.
