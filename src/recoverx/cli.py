"""Command-line interface for RecoverX."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from recoverx._version import __version__
from recoverx.carving.scanner import CarvingScanner
from recoverx.config import CollisionPolicy
from recoverx.domain.candidate import RecoveryCandidate
from recoverx.domain.recovery import RecoveryResult
from recoverx.domain.scan import ScanProgress
from recoverx.filesystems.fat.parser import FatFileSystem
from recoverx.infrastructure.storage.image import DiskImageReader
from recoverx.infrastructure.storage.resolver import FakeVolumeIdentityResolver
from recoverx.services.recovery_service import RecoveryService


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

    candidates: list[RecoveryCandidate] = []
    metadata_offsets: set[int] = set()

    with reader:
        # Step 1: Filesystem Metadata Probe (FAT12/16/32)
        fat_fs = FatFileSystem()
        if fat_fs.detect(reader):
            info = fat_fs.get_fs_info(reader)
            if info is not None and not args.json:
                sys.stderr.write(
                    f"Detected filesystem: {info.fs_type.value} "
                    f"(Label: {info.volume_label or 'None'}, Clusters: {info.total_clusters})\n"
                )
            meta_cands = fat_fs.recover_candidates(
                reader, base_offset=0, include_active=getattr(args, "include_active", False)
            )
            candidates.extend(meta_cands)
            for mc in meta_cands:
                metadata_offsets.add(mc.source_offset)

        # Step 2: Carving Phase (optional or default)
        if not getattr(args, "no_carve", False):
            scanner = CarvingScanner(
                chunk_size_bytes=args.chunk_size,
                overlap_bytes=args.overlap,
                progress_callback=progress_reporter if not args.json else None,
            )
            carved = scanner.scan(reader)
            for c in carved:
                if c.source_offset not in metadata_offsets:
                    candidates.append(c)

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


def _handle_recover(args: argparse.Namespace) -> int:
    """Handle `recoverx recover` command."""
    image_path = Path(args.image).resolve()
    if not image_path.exists():
        sys.stderr.write(f"Error: Disk image not found: {image_path}\n")
        return 1

    dest_dir = Path(args.destination).resolve()

    try:
        reader = DiskImageReader(image_path)
    except Exception as e:
        sys.stderr.write(f"Error opening disk image: {e}\n")
        return 1

    # Map collision policy
    policy = CollisionPolicy.RENAME
    if args.collision_policy == "skip":
        policy = CollisionPolicy.SKIP
    elif args.collision_policy == "never_overwrite":
        policy = CollisionPolicy.OVERWRITE_NEVER

    # Step 1: Scan image for candidates (metadata first, carving optional)
    # Step 2: Initialize recovery service with resolver
    resolver = FakeVolumeIdentityResolver()
    service = RecoveryService(resolver=resolver)

    def progress_callback(
        curr: int, total: int, cand: RecoveryCandidate, res: RecoveryResult
    ) -> None:
        if not args.json:
            sys.stderr.write(
                f"\rRecovering [{curr}/{total}]: {cand.filename} -> {res.status} "
                f"({_format_size(res.bytes_written)})"
            )
            sys.stderr.flush()

    try:
        with reader:
            candidates: list[RecoveryCandidate] = []
            metadata_offsets: set[int] = set()

            fat_fs = FatFileSystem()
            if fat_fs.detect(reader):
                info = fat_fs.get_fs_info(reader)
                if info is not None and not args.json:
                    sys.stderr.write(
                        f"Detected filesystem: {info.fs_type.value} "
                        f"(Label: {info.volume_label or 'None'}, Clusters: {info.total_clusters})\n"
                    )
                meta_cands = fat_fs.recover_candidates(
                    reader, base_offset=0, include_active=getattr(args, "include_active", False)
                )
                candidates.extend(meta_cands)
                for mc in meta_cands:
                    metadata_offsets.add(mc.source_offset)

            if not getattr(args, "no_carve", False):
                scanner = CarvingScanner(chunk_size_bytes=args.chunk_size)
                carved = scanner.scan(reader)
                for c in carved:
                    if c.source_offset not in metadata_offsets:
                        candidates.append(c)

            if not candidates:
                if args.json:
                    sys.stdout.write("[]\n")
                else:
                    sys.stdout.write("No recoverable candidates found in image.\n")
                return 0

            results = service.recover_candidates(
                device=reader,
                destination_directory=dest_dir,
                candidates=candidates,
                collision_policy=policy,
                progress_callback=progress_callback if not args.json else None,
            )
    except Exception as e:
        sys.stderr.write(f"\nError during recovery: {e}\n")
        return 1

    if not args.json:
        sys.stderr.write("\nRecovery operation complete.\n")

    if args.json:
        res_data: list[dict[str, Any]] = []
        for r in results:
            res_data.append(
                {
                    "candidate_id": r.candidate_id,
                    "destination_path": r.destination_path,
                    "bytes_written": r.bytes_written,
                    "status": r.status,
                    "hash_verified": r.hash_verified,
                    "error_message": r.error_message,
                }
            )
        sys.stdout.write(json.dumps(res_data, indent=2) + "\n")
    else:
        sys.stdout.write(f"\nRecovered {len(results)} file(s) to '{dest_dir}':\n")
        sys.stdout.write("-" * 80 + "\n")
        sys.stdout.write(f"{'Status':<18} {'Size':<12} {'Destination Path'}\n")
        sys.stdout.write("-" * 80 + "\n")
        for r in results:
            sys.stdout.write(
                f"{r.status:<18} {_format_size(r.bytes_written):<12} {r.destination_path}\n"
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
    scan_parser.add_argument(
        "--no-carve",
        action="store_true",
        help="Skip raw carving phase (metadata only)",
    )
    scan_parser.add_argument(
        "--include-active",
        action="store_true",
        help="Include active non-deleted files in scan",
    )

    # `recover` command
    recover_parser = subparsers.add_parser(
        "recover", help="Recover files from disk image to a safe destination"
    )
    recover_parser.add_argument("image", help="Path to raw disk image file")
    recover_parser.add_argument("destination", help="Destination directory to save recovered files")
    recover_parser.add_argument(
        "--collision-policy",
        choices=["rename", "skip", "never_overwrite"],
        default="rename",
        help="Action when destination file already exists (default: rename)",
    )
    recover_parser.add_argument(
        "--json",
        action="store_true",
        help="Output recovery results as formatted JSON",
    )
    recover_parser.add_argument(
        "--chunk-size",
        type=int,
        default=1024 * 1024,
        help="Scanner chunk size in bytes (default: 1048576 / 1 MiB)",
    )
    recover_parser.add_argument(
        "--no-carve",
        action="store_true",
        help="Skip raw carving phase (metadata only)",
    )
    recover_parser.add_argument(
        "--include-active",
        action="store_true",
        help="Include active non-deleted files in recovery",
    )

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.command == "scan":
        return _handle_scan(args)
    if args.command == "recover":
        return _handle_recover(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
