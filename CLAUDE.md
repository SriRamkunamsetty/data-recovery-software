# RecoverX: permanent rules for the coding agent

RecoverX is a Windows 10/11 x64 desktop data-recovery app for USB flash drives, SD/memory cards and other block devices. Stack: Python 3.12+, PySide6, SQLite, pytest, pytest-qt, Hypothesis, Ruff, mypy (strict).

The full specification is in `MASTER_PROMPT.md`. The work is split into sessions in `MILESTONES.md`. These rules apply to every session.

## Safety rules (release-blocking, never relax)

1. The source is read-only by construction. `ReadOnlyBlockDevice` exposes only metadata, `size_bytes`, `logical_sector_size`, `read_at(offset, length)` and `close()`. Never add write, erase, format, repair, partition-edit or filesystem-modify operations. Never call `FSCTL_LOCK_VOLUME`, `FSCTL_DISMOUNT_VOLUME` or anything else that changes device or volume state.
2. Nothing the app creates goes on the source device or on any volume of the same physical disk: recovered files, images, the session database, logs and temp files all count. Validate this for the work directory as well as the destination.
3. If source/destination separation or device identity cannot be established with confidence, refuse and explain why. Never fall back to a weaker check.
4. Recovered content is untrusted. Never execute it, never auto-open it, always apply size and resource limits.
5. No network access in core recovery. Never transmit logs, filenames or file contents.
6. Never claim success you have not verified. No fake devices, progress, hashes, test results or recovery statistics in production code. Demo mode must be clearly labelled.
7. No percentage "recovery probability". Use factual statuses only: Metadata recovered, Signature matched, Preview validated, Partially readable, Truncated, Unverified, Recovery failed.
8. A feature whose interface exists but whose logic does not is **not implemented**. Mark it as unsupported in the UI and docs instead of returning empty results.

## How to work

- Do only the milestone named in the prompt. When it is done and its checks pass, stop and report. Put ideas for extra work in the report instead of building them.
- At the start of a session read `PROGRESS.md`, `docs/DECISIONS.md` and the milestone text. At the end update `PROGRESS.md` (what is truly done, what is partial, known issues) and record any design decision in `docs/DECISIONS.md`.
- Run the real checks before reporting done: `pytest`, `ruff check`, `ruff format --check`, `mypy`. Paste real results. If a check cannot run here (for example Windows-only code on Linux), say exactly which one and why. Do not call a feature done on a syntax check alone.
- Fix regressions before moving on. Never weaken or delete a test to make it pass.
- Windows-only code lives in `devices/windows_*` and imports `ctypes.windll` lazily, so the core package imports and its tests run on any OS. Qt tests run headless with `QT_QPA_PLATFORM=offscreen`.
- Use explicit constructor dependencies. The UI never touches raw devices; it calls application services.
- Validate every offset, length and count read from disk before use, with overflow-safe arithmetic.
- Do not add large dependencies without a written reason in `DECISIONS.md`. Check each dependency's license before adding it.
- Never copy code from GPL projects (TestDisk, PhotoRec, ddrescue, Sleuth Kit). Reimplement from format specifications. Third-party tools may be used only as dev-time comparison oracles and are never bundled.
- Hardware tests use disposable media only and are never run automatically.

## Report format at the end of each session

1. Files created or modified.
2. Check results (real output summary).
3. What is complete, what is partial, what is not implemented.
4. Blockers, with the exact next step.
