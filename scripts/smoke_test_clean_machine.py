"""Clean-Machine Smoke Test Script for RecoverX.

Designed to execute on a target Windows 10/11 x64 test machine to verify that:
1. The packaged executable (or Python environment) launches cleanly without missing dependencies.
2. CLI subcommands (--help, --version, scan, recover, partitions, image, gui) work as expected.
3. Destination safety enforcement prevents writing to unsafe destinations.
4. Out-of-process preview sandbox runs safely without hanging.
5. End-to-end scanning and extraction succeeds on synthetic media.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


class SmokeTestRunner:
    def __init__(self, target_cmd: list[str]) -> None:
        self.cmd = target_cmd
        self.results: list[tuple[str, bool, str]] = []
        self.temp_dir = Path(tempfile.mkdtemp(prefix="recoverx_smoke_"))

    def cleanup(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def run_check(self, name: str, test_fn: object) -> bool:
        start = time.perf_counter()
        try:
            test_fn()  # type: ignore[operator]
            elapsed = time.perf_counter() - start
            self.results.append((name, True, f"Passed ({elapsed:.2f}s)"))
            print(f"  [PASS] {name} ({elapsed:.2f}s)")
            return True
        except Exception as exc:
            elapsed = time.perf_counter() - start
            self.results.append((name, False, f"FAILED: {exc}"))
            print(f"  [FAIL] {name} ({elapsed:.2f}s): {exc}")
            return False

    def test_version(self) -> None:
        res = subprocess.run(
            [*self.cmd, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if res.returncode != 0:
            raise RuntimeError(f"Return code {res.returncode}: {res.stderr}")
        if "1.0.0" not in res.stdout and "0.1.0" not in res.stdout:
            raise RuntimeError(f"Unexpected version output: {res.stdout.strip()}")

    def test_help(self) -> None:
        res = subprocess.run(
            [*self.cmd, "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if res.returncode != 0:
            raise RuntimeError(f"Return code {res.returncode}: {res.stderr}")
        for subcommand in ["scan", "recover", "partitions", "image", "gui"]:
            if subcommand not in res.stdout:
                raise RuntimeError(f"Missing subcommand '{subcommand}' in help output")

    def test_preview_sandbox_worker(self) -> None:
        import struct
        import zlib

        # Construct valid 1x1 PNG image with proper CRC32 and zlib IDAT
        buf = bytearray(b"\x89PNG\r\n\x1a\n")
        ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data)
        buf.extend(struct.pack(">I4s", len(ihdr_data), b"IHDR"))
        buf.extend(ihdr_data)
        buf.extend(struct.pack(">I", ihdr_crc))

        raw_scanline = b"\x00\xff\x00\x00"
        idat_data = zlib.compress(raw_scanline)
        idat_crc = zlib.crc32(b"IDAT" + idat_data)
        buf.extend(struct.pack(">I4s", len(idat_data), b"IDAT"))
        buf.extend(idat_data)
        buf.extend(struct.pack(">I", idat_crc))

        iend_crc = zlib.crc32(b"IEND")
        buf.extend(struct.pack(">I4s", 0, b"IEND"))
        buf.extend(struct.pack(">I", iend_crc))

        res = subprocess.run(
            [*self.cmd, "preview-worker", "--ext=png", "--max-dim=512"],
            input=bytes(buf),
            capture_output=True,
            timeout=10,
        )
        if res.returncode != 0:
            raise RuntimeError(f"Worker returncode {res.returncode}: {res.stderr.decode()}")
        out_json = json.loads(res.stdout.decode("utf-8").strip())
        if not out_json.get("success"):
            raise RuntimeError(f"Worker reported error: {out_json.get('error')}")

    def test_destination_safety(self) -> None:
        # Create a dummy image
        img_path = self.temp_dir / "safe_test.raw"
        img_path.write_bytes(b"\x00" * 1024 * 1024)

        # Attempt recovery targeting the same directory as the image
        res = subprocess.run(
            [*self.cmd, "recover", str(img_path), str(self.temp_dir)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Must fail or refuse destination because destination contains the source image!
        if res.returncode == 0:
            raise RuntimeError(
                "Destination safety guard failed to block recovery to source folder!"
            )

    def test_scan_and_recovery(self) -> None:
        # Construct a synthetic disk image with a valid MBR and a JPEG file block
        img_dir = self.temp_dir / "source_media"
        img_dir.mkdir(exist_ok=True)
        img_path = img_dir / "synthetic_test.img"
        dest_path = self.temp_dir / "recovered_output"
        dest_path.mkdir(exist_ok=True)

        # 512-byte MBR sector with 0x55AA signature
        mbr = bytearray(512)
        mbr[510:512] = b"\x55\xaa"

        # Valid minimal JPEG
        jpeg_data = (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            b"\xff\xdb\x00C\x00"
            + (b"\x01" * 64)
            + b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
            b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00"
            b"\xff\xd9"
        )
        # Pad JPEG to 512 bytes alignment
        payload = bytearray(1024 * 64)
        payload[0:512] = mbr
        payload[2048 : 2048 + len(jpeg_data)] = jpeg_data
        img_path.write_bytes(payload)

        # Run scan
        res = subprocess.run(
            [*self.cmd, "scan", str(img_path), "--json"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if res.returncode != 0:
            raise RuntimeError(f"Scan failed (code {res.returncode}): {res.stderr}")

        scan_out = json.loads(res.stdout)
        if not isinstance(scan_out, list) or len(scan_out) < 1:
            raise RuntimeError(f"Scan found no candidates: {res.stdout}")

        # Run recovery
        res_rec = subprocess.run(
            [*self.cmd, "recover", str(img_path), str(dest_path), "--json"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if res_rec.returncode != 0:
            raise RuntimeError(f"Recovery failed (code {res_rec.returncode}): {res_rec.stderr}")

        rec_files = list(dest_path.rglob("*.jpg"))
        if not rec_files:
            raise RuntimeError(f"No recovered .jpg file found in {dest_path}")

    def run_all(self) -> int:
        print("=== Starting RecoverX Clean-Machine Smoke Tests ===")
        print(f"Target Command: {' '.join(self.cmd)}")
        print(f"Working Temp:   {self.temp_dir}")
        print()

        self.run_check("CLI --version check", self.test_version)
        self.run_check("CLI --help and subcommand listing", self.test_help)
        self.run_check("Preview sandbox worker subprocess", self.test_preview_sandbox_worker)
        self.run_check("Destination safety invariant", self.test_destination_safety)
        self.run_check("End-to-end carving & recovery", self.test_scan_and_recovery)

        print()
        print("=== Smoke Test Results Summary ===")
        all_passed = True
        for name, passed, details in self.results:
            status = "PASS" if passed else "FAIL"
            print(f"  [{status}] {name:<35} : {details}")
            if not passed:
                all_passed = False

        self.cleanup()
        return 0 if all_passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="RecoverX Clean-Machine Smoke Test")
    parser.add_argument(
        "--exe",
        help="Path to packaged recoverx.exe. If omitted, uses virtualenv python -m recoverx.cli",
    )
    args = parser.parse_args()

    if args.exe:
        cmd = [str(Path(args.exe).resolve())]
    else:
        # Check if dist/recoverx/recoverx.exe exists
        default_dist_exe = Path("dist/recoverx/recoverx.exe")
        if default_dist_exe.exists():
            cmd = [str(default_dist_exe.resolve())]
        else:
            cmd = [sys.executable, "-m", "recoverx.cli"]

    runner = SmokeTestRunner(cmd)
    return runner.run_all()


if __name__ == "__main__":
    sys.exit(main())
