"""Command-line interface for RecoverX."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from recoverx._version import __version__
from recoverx.carving.scanner import CarvingScanner
from recoverx.domain.scan import ScanProgress
from recoverx.infrastructure.storage.image import DiskImageReader


def _format_size(size_bytes: int) -> str:
    """Format byte size into human-readable string."""
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    val = float(size_bytes)
    for unit in units:
        if val < 1024.0 or unit == units[-1]:
            return f"{val:.2f} {unit}"
        val /= 1024.0
    return f"{size_bytes} B"


def _handle_scan(args: argparse.Namespace) -> int:
    """Handle `recoverx scan` command."""
    image_path = Path(args.image).resolve()
    if not image_path.exists():
        sys.stderr.write(f"Error: Disk image not found: {image_path}\n")
        return 1

    try:
        reader = DiskImageReader(image_path)
    except Exception as e:
        sys.stderr.write(f"Error opening disk image: {e}\n")
        return 1

    def progress_reporter(prog: ScanProgress) -> None:
        if not args.json:
            sys.stderr.write(
                f"\rScanning: {prog.progress_percent:.1f}% "
                f"({_format_size(prog.bytes_scanned)} / {_format_size(prog.total_bytes)}) | "
                f"Candidates: {prog.candidates_found} | Bad Sectors: {prog.bad_sectors_found}"
            )
            sys.stderr.flush()

    scanner = CarvingScanner(
        chunk_size_bytes=args.chunk_size,
        overlap_bytes=args.overlap,
        progress_callback=progress_reporter if not args.json else None,
    )

    with reader:
        candidates = scanner.scan(reader)

    if not args.json:
        sys.stderr.write("\nScan complete.\n")

    if args.json:
        output_data: list[dict[str, Any]] = []
        for c in candidates:
            output_data.append(
                {
                    "id": c.candidate_id,
                    "filename": c.filename,
                    "relative_path": c.relative_path,
                    "extension": c.extension,
                    "size_bytes": c.size_bytes,
                    "source_offset": c.source_offset,
                    "status": c.status.value,
                    "sha256": c.sha256_hash,
                    "notes": c.notes,
                }
            )
        sys.stdout.write(json.dumps(output_data, indent=2) + "\n")
    else:
        sys.stdout.write(f"\nDiscovered {len(candidates)} candidate(s):\n")
        sys.stdout.write("-" * 80 + "\n")
        sys.stdout.write(
            f"{'Offset':<12} {'Extension':<10} {'Size':<12} {'Status':<22} {'Filename'}\n"
        )
        sys.stdout.write("-" * 80 + "\n")
        for c in candidates:
            sys.stdout.write(
                f"0x{c.source_offset:08X}   {c.extension:<10} {_format_size(c.size_bytes):<12} "
                f"{c.status.value:<22} {c.filename}\n"
            )
        sys.stdout.write("-" * 80 + "\n")

    return 0


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="recoverx",
        description="Forensic-grade, non-destructive data recovery application",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command")

    # `scan` command
    scan_parser = subparsers.add_parser("scan", help="Scan disk image for recoverable files")
    scan_parser.add_argument("image", help="Path to raw disk image file")
    scan_parser.add_argument(
        "--json",
        action="store_true",
        help="Output candidate results as formatted JSON",
    )
    scan_parser.add_argument(
        "--chunk-size",
        type=int,
        default=1024 * 1024,
        help="Scanner chunk size in bytes (default: 1048576 / 1 MiB)",
    )
    scan_parser.add_argument(
        "--overlap",
        type=int,
        default=64 * 1024,
        help="Scanner chunk overlap in bytes (default: 65536 / 64 KiB)",
    )

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.command == "scan":
        return _handle_scan(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
