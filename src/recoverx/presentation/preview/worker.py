"""Isolated subprocess worker for untrusted file previews."""

import base64
import contextlib
import io
import json
import struct
import sys
import zipfile
from typing import Any

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage

MAX_PREVIEW_INPUT_BYTES = 10 * 1024 * 1024  # 10 MiB limit
MAX_IMAGE_DIM = 4096  # Max width/height to prevent memory exhaustion


def preview_image(data: bytes, ext: str, max_dim: int) -> dict[str, Any]:
    """Decode image in-process and return downscaled PNG base64."""
    img = QImage()
    if not img.loadFromData(data):
        return {
            "success": False,
            "preview_type": "error",
            "error": "Failed to decode image data; stream may be corrupt or truncated.",
        }

    w, h = img.width(), img.height()
    if w <= 0 or h <= 0:
        return {
            "success": False,
            "preview_type": "error",
            "error": f"Invalid image dimensions: {w}x{h}",
        }

    # Downscale if exceeding max_dim
    if w > max_dim or h > max_dim:
        img = img.scaled(
            max_dim,
            max_dim,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    # Encode to PNG base64
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")  # type: ignore[call-overload]
    png_bytes = buf.data().data()
    buf.close()

    b64_str = base64.b64encode(png_bytes).decode("ascii")
    return {
        "success": True,
        "preview_type": "image",
        "metadata": {
            "width": w,
            "height": h,
            "display_width": img.width(),
            "display_height": img.height(),
            "format": ext.upper(),
        },
        "image_b64": b64_str,
    }


def preview_text(data: bytes, ext: str) -> dict[str, Any]:
    """Decode text and sanitize control characters."""
    snippet = data[: 64 * 1024]
    try:
        text = snippet.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        text = snippet.decode("latin-1", errors="replace")
        encoding = "latin-1"

    # Sanitize control characters except newline and tab
    sanitized = "".join(ch if ch in ("\n", "\r", "\t") or ch >= " " else " " for ch in text)
    lines = sanitized.splitlines()

    return {
        "success": True,
        "preview_type": "text",
        "metadata": {
            "lines_count": len(lines),
            "bytes_previewed": len(snippet),
            "encoding": encoding,
        },
        "content": sanitized,
    }


def preview_audio(data: bytes, ext: str) -> dict[str, Any]:
    """Extract audio container metadata without audio playback."""
    if ext == "wav" and len(data) >= 36 and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        # Parse fmt chunk
        fmt_idx = data.find(b"fmt ")
        if fmt_idx != -1 and len(data) >= fmt_idx + 24:
            channels = struct.unpack("<H", data[fmt_idx + 10 : fmt_idx + 12])[0]
            sample_rate = struct.unpack("<I", data[fmt_idx + 12 : fmt_idx + 16])[0]
            byte_rate = struct.unpack("<I", data[fmt_idx + 16 : fmt_idx + 20])[0]
            bits_per_sample = struct.unpack("<H", data[fmt_idx + 22 : fmt_idx + 24])[0]

            duration_sec = 0.0
            data_idx = data.find(b"data")
            if data_idx != -1 and len(data) >= data_idx + 8 and byte_rate > 0:
                data_len = struct.unpack("<I", data[data_idx + 4 : data_idx + 8])[0]
                duration_sec = round(data_len / byte_rate, 2)

            return {
                "success": True,
                "preview_type": "audio",
                "metadata": {
                    "format": "WAV (PCM)",
                    "channels": "Stereo"
                    if channels == 2
                    else "Mono"
                    if channels == 1
                    else str(channels),
                    "sample_rate": f"{sample_rate:,} Hz",
                    "bits_per_sample": f"{bits_per_sample}-bit",
                    "duration": f"{duration_sec:.1f} seconds" if duration_sec > 0 else "Unknown",
                },
            }

    # MP3 metadata
    has_id3 = data[:3] == b"ID3"
    title, artist, album = "", "", ""
    if has_id3 and len(data) >= 10:
        # Simple ID3 tag search
        for tag, attr in [
            (b"TIT2", "title"),
            (b"TPE1", "artist"),
            (b"TALB", "album"),
        ]:
            pos = data.find(tag, 10, min(len(data), 4096))
            if pos != -1 and len(data) >= pos + 10:
                sz = struct.unpack(">I", data[pos + 4 : pos + 8])[0]
                if 0 < sz < 256 and len(data) >= pos + 10 + sz:
                    val = (
                        data[pos + 10 : pos + 10 + sz]
                        .decode("utf-8", errors="ignore")
                        .strip("\x00")
                    )
                    if attr == "title":
                        title = val
                    elif attr == "artist":
                        artist = val
                    elif attr == "album":
                        album = val

    return {
        "success": True,
        "preview_type": "audio",
        "metadata": {
            "format": "MP3 Audio",
            "title": title or "Unknown",
            "artist": artist or "Unknown",
            "album": album or "Unknown",
            "id3_present": "Yes" if has_id3 else "No",
        },
    }


def preview_video(data: bytes, ext: str) -> dict[str, Any]:
    """Extract video container metadata without video decoding."""
    metadata: dict[str, Any] = {"format": ext.upper()}

    if ext in ("mp4", "mov", "m4a") and len(data) >= 16:
        # Parse ftyp major brand
        if data[4:8] == b"ftyp":
            brand = data[8:12].decode("ascii", errors="replace").strip()
            metadata["major_brand"] = brand

        # Search for mvhd (movie header)
        mvhd_pos = data.find(b"mvhd")
        if mvhd_pos != -1 and len(data) >= mvhd_pos + 28:
            timescale = struct.unpack(">I", data[mvhd_pos + 16 : mvhd_pos + 20])[0]
            duration = struct.unpack(">I", data[mvhd_pos + 20 : mvhd_pos + 24])[0]
            if timescale > 0:
                dur_sec = duration / timescale
                metadata["duration"] = f"{dur_sec:.1f} seconds"

    elif ext == "avi" and len(data) >= 32 and data[:4] == b"RIFF" and data[8:12] == b"AVI ":
        # Search for avih
        avih_pos = data.find(b"avih")
        if avih_pos != -1 and len(data) >= avih_pos + 44:
            w = struct.unpack("<I", data[avih_pos + 36 : avih_pos + 40])[0]
            h = struct.unpack("<I", data[avih_pos + 40 : avih_pos + 44])[0]
            metadata["dimensions"] = f"{w}x{h} px"

    return {
        "success": True,
        "preview_type": "video",
        "metadata": metadata,
    }


def preview_sqlite(data: bytes) -> dict[str, Any]:
    """Extract SQLite database schema and table list safely."""
    if len(data) < 100 or data[:16] != b"SQLite format 3\x00":
        return {
            "success": False,
            "preview_type": "error",
            "error": "Invalid SQLite database signature",
        }

    raw_page_size = struct.unpack(">H", data[16:18])[0]
    page_size = 65536 if raw_page_size == 1 else raw_page_size
    page_count = struct.unpack(">I", data[28:32])[0]
    encoding_code = struct.unpack(">I", data[56:60])[0]
    enc_name = {1: "UTF-8", 2: "UTF-16le", 3: "UTF-16be"}.get(encoding_code, "Unknown")

    return {
        "success": True,
        "preview_type": "sqlite",
        "metadata": {
            "format": "SQLite 3 Database",
            "page_size": f"{page_size} bytes",
            "total_pages": str(page_count),
            "total_size": f"{page_size * page_count:,} bytes",
            "text_encoding": enc_name,
        },
    }


def preview_zip(data: bytes, ext: str) -> dict[str, Any]:
    """Inspect ZIP archive entries with zip-slip safety protection."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infolist = zf.infolist()
            total_entries = len(infolist)
            entries: list[dict[str, Any]] = []

            has_zip_slip = False
            for item in infolist[:500]:  # Limit to 500 entries
                # Check for zip slip path traversal
                if item.filename.startswith("/") or ".." in item.filename.split("/"):
                    has_zip_slip = True

                entries.append(
                    {
                        "name": item.filename,
                        "size": item.file_size,
                        "compressed": item.compress_size,
                    }
                )

            # Classify Office documents
            doc_type = "ZIP Archive"
            names = {e.filename for e in infolist}
            if "word/document.xml" in names:
                doc_type = "Microsoft Word Document (.docx)"
            elif "xl/workbook.xml" in names:
                doc_type = "Microsoft Excel Spreadsheet (.xlsx)"
            elif "ppt/presentation.xml" in names:
                doc_type = "Microsoft PowerPoint Presentation (.pptx)"

            return {
                "success": True,
                "preview_type": "archive",
                "metadata": {
                    "document_type": doc_type,
                    "total_entries": total_entries,
                    "shown_entries": len(entries),
                    "zip_slip_risk": "DETECTED (Dangerous)" if has_zip_slip else "None",
                },
                "entries": entries,
            }
    except Exception as exc:
        return {
            "success": False,
            "preview_type": "error",
            "error": f"Failed to parse ZIP structure: {exc}",
        }


def main(argv: list[str] | None = None) -> int:
    """Main worker entry point invoked as an isolated subprocess."""
    ext = "bin"
    max_dim = MAX_IMAGE_DIM
    args_list = argv if argv is not None else sys.argv[1:]
    for arg in args_list:
        if arg.startswith("--ext="):
            ext = arg.split("=", 1)[1].lower().lstrip(".")
        elif arg.startswith("--max-dim="):
            with contextlib.suppress(ValueError):
                max_dim = int(arg.split("=", 1)[1])

    try:
        # Read raw candidate bytes from stdin
        raw_data = sys.stdin.buffer.read(MAX_PREVIEW_INPUT_BYTES)
        if not raw_data:
            res = {
                "success": False,
                "preview_type": "error",
                "error": "Empty input buffer (0 bytes)",
            }
            print(json.dumps(res))
            return 0

        # Route by format category
        if ext in ("jpg", "jpeg", "png", "gif", "bmp", "webp"):
            res = preview_image(raw_data, ext, max_dim)
        elif ext in ("txt", "log", "csv", "json", "xml", "ini", "md", "py", "c", "h"):
            res = preview_text(raw_data, ext)
        elif ext in ("wav", "mp3"):
            res = preview_audio(raw_data, ext)
        elif ext in ("mp4", "mov", "m4a", "avi"):
            res = preview_video(raw_data, ext)
        elif ext in ("sqlite", "db", "sqlite3"):
            res = preview_sqlite(raw_data)
        elif ext in ("zip", "docx", "xlsx", "pptx"):
            res = preview_zip(raw_data, ext)
        else:
            # Generic binary preview
            res = {
                "success": True,
                "preview_type": "metadata",
                "metadata": {
                    "format": f"Binary Data ({ext.upper()})",
                    "preview_bytes": len(raw_data),
                    "hex_sample": raw_data[:32].hex(" ").upper(),
                },
            }

        print(json.dumps(res))
        return 0
    except Exception as exc:
        err_res = {
            "success": False,
            "preview_type": "error",
            "error": f"Worker internal error: {exc}",
        }
        print(json.dumps(err_res))
        return 0


if __name__ == "__main__":
    sys.exit(main())
