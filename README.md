# RecoverX

RecoverX is a local-first, forensic-grade Windows 10/11 x64 desktop data recovery application for USB flash drives, SD/memory cards, and raw disk images.

## Core Principles

1. **Strictly Read-Only Source**: Hardware access primitives never issue write or format instructions.
2. **Strict Destination Separation**: Recovered data and application runtime state (databases, logs, temp files) are strictly prohibited from residing on the source device or physical disk.
3. **Factual Statuses**: No misleading percentage guarantees. File recovery state is reported factually (*Metadata recovered*, *Signature matched*, *Preview validated*, *Partially readable*, *Truncated*, *Unverified*, *Recovery failed*).
4. **Safety & Privacy**: 100% offline; zero network calls; unverified/recovered content is treated as untrusted.

## Development Setup

Requirements:
- Python 3.12 (specifically tested against 3.12.13)
- `uv` (recommended) or `pip`

```bash
# Create virtual environment
uv venv --python 3.12
.venv\Scripts\activate   # Windows
# or: source .venv/bin/activate  # Linux

# Install dependencies in editable mode
uv pip install -e ".[dev]"

# Run code checks
ruff check .
ruff format --check .
mypy src tests
pytest
```

## Milestone Status

See `PROGRESS.md` for current milestone tracking and completion reports.
Architecture decisions are tracked in `docs/DECISIONS.md`.
