"""Sandboxed untrusted file preview executor with timeout and resource limits."""

import json
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

MAX_PREVIEW_INPUT_BYTES = 10 * 1024 * 1024  # 10 MiB limit


@dataclass(frozen=True)
class PreviewResult:
    """Outcome of sandboxed preview generation."""

    success: bool
    preview_type: str  # "image", "text", "audio", "video", "sqlite", "archive", "metadata", "error"
    metadata: dict[str, Any] = field(default_factory=dict)
    content: str = ""
    image_b64: str = ""
    entries: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""


class PreviewSandbox:
    """Executes untrusted file preview decoding inside an isolated, killable subprocess.

    Section 11 of MASTER_PROMPT.md:
    Recovered files are untrusted. Previews run with strict limits (size,
    dimensions, decode time) in a separate low-privilege subprocess that can be killed.
    Preview success alone sets status; failure sets 'Unverified' with reason, never a crash.
    """

    def __init__(self, default_timeout_sec: float = 3.0) -> None:
        self.default_timeout = default_timeout_sec

    def generate_preview(
        self,
        data: bytes,
        extension: str,
        timeout_sec: float | None = None,
        max_dim: int = 4096,
    ) -> PreviewResult:
        """Run worker in subprocess with memory and time caps."""
        if not data:
            return PreviewResult(
                success=False,
                preview_type="error",
                error="Empty candidate payload (0 bytes).",
            )

        timeout = timeout_sec or self.default_timeout
        ext_clean = extension.lower().lstrip(".")
        limited_data = data[:MAX_PREVIEW_INPUT_BYTES]

        if getattr(sys, "frozen", False):
            cmd = [
                sys.executable,
                "preview-worker",
                f"--ext={ext_clean}",
                f"--max-dim={max_dim}",
            ]
        else:
            cmd = [
                sys.executable,
                "-m",
                "recoverx.presentation.preview.worker",
                f"--ext={ext_clean}",
                f"--max-dim={max_dim}",
            ]

        try:
            proc = subprocess.run(
                cmd,
                input=limited_data,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            logger.warning("Preview subprocess timed out after %.1fs on .%s", timeout, ext_clean)
            return PreviewResult(
                success=False,
                preview_type="error",
                error=f"Preview timed out ({timeout:.1f}s limit exceeded). Process killed safely.",
            )
        except Exception as exc:
            logger.exception("Failed to launch preview worker: %s", exc)
            return PreviewResult(
                success=False,
                preview_type="error",
                error=f"Could not spawn preview sandbox: {exc}",
            )

        if proc.returncode != 0:
            err_msg = proc.stderr.decode("utf-8", errors="replace").strip()
            return PreviewResult(
                success=False,
                preview_type="error",
                error=f"Preview subprocess failed (code {proc.returncode}): {err_msg}",
            )

        out_text = proc.stdout.decode("utf-8", errors="replace").strip()
        if not out_text:
            return PreviewResult(
                success=False,
                preview_type="error",
                error="Preview worker returned empty output.",
            )

        try:
            data_dict = json.loads(out_text)
            return PreviewResult(
                success=bool(data_dict.get("success", False)),
                preview_type=str(data_dict.get("preview_type", "error")),
                metadata=dict(data_dict.get("metadata", {})),
                content=str(data_dict.get("content", "")),
                image_b64=str(data_dict.get("image_b64", "")),
                entries=list(data_dict.get("entries", [])),
                error=str(data_dict.get("error", "")),
            )
        except json.JSONDecodeError as exc:
            return PreviewResult(
                success=False,
                preview_type="error",
                error=f"Malformed response from preview worker: {exc}",
            )
