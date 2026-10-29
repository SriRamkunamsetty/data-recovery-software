"""Compute cryptographic SHA-256 checksums for release distributions and binaries."""

import hashlib
import sys
from pathlib import Path


def sha256_file(filepath: Path) -> str:
    """Compute hex SHA-256 digest of a binary file using 64 KiB chunks."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def generate_checksums(target_dir: Path, output_file: Path | None = None) -> Path:
    """Generate SHA256SUMS.txt for all distribution files in target_dir."""
    if not target_dir.exists():
        raise FileNotFoundError(f"Directory not found: {target_dir}")

    out_path = output_file or (target_dir / "SHA256SUMS.txt")
    entries: list[str] = []

    print(f"Generating SHA-256 checksums for files in: {target_dir}")
    for item in sorted(target_dir.rglob("*")):
        if item.is_file() and item.name != "SHA256SUMS.txt":
            checksum = sha256_file(item)
            rel_path = item.relative_to(target_dir).as_posix()
            line = f"{checksum}  {rel_path}"
            entries.append(line)
            print(f"  {checksum[:16]}...  {rel_path}")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(entries) + "\n")

    print(f"Checksum manifest written to: {out_path}")
    return out_path


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dist")
    if not target.exists():
        print(f"Target directory {target} does not exist.")
        return 1
    generate_checksums(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
