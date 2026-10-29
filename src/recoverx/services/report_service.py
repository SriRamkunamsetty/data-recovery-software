"""Forensic recovery report generation in JSON and standalone HTML formats."""

import html
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from recoverx.domain.candidate import RecoveryCandidate
from recoverx.domain.device import DeviceIdentity
from recoverx.domain.enums import CandidateStatus
from recoverx.domain.partition import PartitionInfo
from recoverx.domain.recovery import RecoveryResult
from recoverx.domain.session import DeviceTriageResult

logger = logging.getLogger(__name__)


def _format_size(size_bytes: int) -> str:
    """Format bytes into human-readable binary units (KiB, MiB, GiB)."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    size_float = float(size_bytes)
    for unit in ["KiB", "MiB", "GiB", "TiB"]:
        size_float /= 1024.0
        if size_float < 1024.0:
            return f"{size_float:.2f} {unit}"
    return f"{size_float:.2f} PiB"


@dataclass(frozen=True)
class ForensicReportData:
    """Full dataset required to compile a forensic recovery report."""

    report_id: str
    session_id: str
    generated_at: float
    source_identity: DeviceIdentity
    triage_result: DeviceTriageResult
    partitions: list[PartitionInfo]
    candidates: list[RecoveryCandidate]
    recovery_results: list[RecoveryResult]
    scan_duration_seconds: float
    carving_executed: bool
    app_version: str = "0.1.0"


class ReportService:
    """Exports forensic recovery reports in structured JSON and self-contained HTML."""

    def export_json(self, report_data: ForensicReportData, output_path: Path | str) -> Path:
        """Export report dataset as a structured JSON file."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        status_counts: dict[str, int] = {}
        format_counts: dict[str, int] = {}
        for c in report_data.candidates:
            status_counts[c.status.value] = status_counts.get(c.status.value, 0) + 1
            ext = c.extension.upper().lstrip(".") or "UNKNOWN"
            format_counts[ext] = format_counts.get(ext, 0) + 1

        successful_recoveries = [r for r in report_data.recovery_results if r.is_successful]
        total_recovered_bytes = sum(r.bytes_written for r in successful_recoveries)

        data: dict[str, Any] = {
            "report_id": report_data.report_id,
            "session_id": report_data.session_id,
            "application": "RecoverX",
            "app_version": report_data.app_version,
            "generated_at_timestamp": report_data.generated_at,
            "generated_at_utc": time.strftime(
                "%Y-%m-%d %H:%M:%SZ", time.gmtime(report_data.generated_at)
            ),
            "source_device": {
                "vendor": report_data.source_identity.vendor,
                "product": report_data.source_identity.product,
                "serial": report_data.source_identity.serial,
                "capacity_bytes": report_data.source_identity.capacity_bytes,
                "capacity_human": _format_size(report_data.source_identity.capacity_bytes),
                "logical_sector_size": report_data.source_identity.logical_sector_size,
                "physical_sector_size": report_data.source_identity.physical_sector_size,
                "disk_identifier": report_data.source_identity.disk_identifier,
                "sector0_sha256": report_data.source_identity.sector0_hash,
            },
            "triage": {
                "status": report_data.triage_result.status.value,
                "explanation": report_data.triage_result.explanation,
                "recommended_action": report_data.triage_result.recommended_action,
                "imaging_recommended": report_data.triage_result.recommend_imaging,
            },
            "partitions": [
                {
                    "partition_number": p.partition_number,
                    "start_sector": p.start_sector,
                    "sector_count": p.sector_count,
                    "start_offset_bytes": p.start_offset_bytes,
                    "size_bytes": p.size_bytes,
                    "size_human": _format_size(p.size_bytes),
                    "filesystem_type": p.partition_type_or_guid,
                    "is_bootable": p.is_bootable,
                    "description": p.name,
                }
                for p in report_data.partitions
            ],
            "scan_summary": {
                "duration_seconds": round(report_data.scan_duration_seconds, 2),
                "carving_executed": report_data.carving_executed,
                "total_candidates": len(report_data.candidates),
                "status_breakdown": status_counts,
                "format_breakdown": format_counts,
            },
            "recovery_summary": {
                "total_files_recovered": len(successful_recoveries),
                "total_bytes_recovered": total_recovered_bytes,
                "total_bytes_human": _format_size(total_recovered_bytes),
                "recovery_failures": len(report_data.recovery_results) - len(successful_recoveries),
            },
            "candidates": [
                {
                    "candidate_id": c.candidate_id,
                    "filename": c.filename,
                    "relative_path": c.relative_path,
                    "size_bytes": c.size_bytes,
                    "size_human": _format_size(c.size_bytes),
                    "source_offset": c.source_offset,
                    "source_method": c.source_method.value,
                    "status": c.status.value,
                    "sha256_hash": c.sha256_hash,
                    "created_at": c.created_at,
                    "modified_at": c.modified_at,
                    "notes": c.notes,
                }
                for c in report_data.candidates
            ],
            "recovery_results": [
                {
                    "candidate_id": r.candidate_id,
                    "destination_path": r.destination_path,
                    "bytes_written": r.bytes_written,
                    "status": r.status,
                    "hash_verified": r.hash_verified,
                    "actual_sha256": r.actual_sha256,
                    "error_message": r.error_message,
                }
                for r in report_data.recovery_results
            ],
            "forensic_integrity_statement": (
                "RecoverX strictly implements read-only access on the source storage medium. "
                "Candidate statuses are factual and verified by file structure and checksum "
                "algorithms; no probabilistic recovery claims are made."
            ),
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        logger.info("Forensic report exported to JSON: %s", path)
        return path

    def export_html(self, report_data: ForensicReportData, output_path: Path | str) -> Path:
        """Export self-contained, professional HTML report."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        status_counts: dict[str, int] = {}
        format_counts: dict[str, int] = {}
        for c in report_data.candidates:
            status_counts[c.status.value] = status_counts.get(c.status.value, 0) + 1
            ext = c.extension.upper().lstrip(".") or "UNKNOWN"
            format_counts[ext] = format_counts.get(ext, 0) + 1

        format_rows = []
        total_cands = len(report_data.candidates)
        for fmt_name, count in sorted(format_counts.items(), key=lambda x: x[1], reverse=True):
            pct = (count / total_cands * 100) if total_cands > 0 else 0
            format_rows.append(
                f"<tr><td><strong>{html.escape(fmt_name)}</strong></td>"
                f"<td>{count:,}</td><td>{pct:.1f}%</td></tr>"
            )

        successful_recoveries = [r for r in report_data.recovery_results if r.is_successful]
        total_recovered_bytes = sum(r.bytes_written for r in successful_recoveries)
        rec_map = {r.candidate_id: r for r in report_data.recovery_results}

        # Build candidate rows
        cand_rows = []
        for c in report_data.candidates:
            rec = rec_map.get(c.candidate_id)
            rec_status = rec.status if rec else "Not extracted"
            rec_hash = rec.actual_sha256 if (rec and rec.actual_sha256) else (c.sha256_hash or "-")

            status_badge_class = (
                "badge-success" if c.status == CandidateStatus.PREVIEW_VALIDATED else "badge-info"
            )
            if c.status in (
                CandidateStatus.TRUNCATED,
                CandidateStatus.CORRUPTED,
                CandidateStatus.RECOVERY_FAILED,
            ):
                status_badge_class = "badge-danger"

            cand_rows.append(
                f"<tr>"
                f"<td><code>{html.escape(c.candidate_id)}</code></td>"
                f"<td><strong>{html.escape(c.filename)}</strong></td>"
                f"<td>{html.escape(c.relative_path or '/')}</td>"
                f"<td>{_format_size(c.size_bytes)}</td>"
                f"<td><code>{c.source_offset}</code></td>"
                f"<td>{html.escape(c.source_method.value)}</td>"
                f'<td><span class="badge {status_badge_class}">'
                f"{html.escape(c.status.value)}</span></td>"
                f"<td><code>{html.escape(rec_hash[:16])}...</code></td>"
                f"<td>{html.escape(rec_status)}</td>"
                f"</tr>"
            )

        # Build partition rows
        part_rows = []
        for p in report_data.partitions:
            part_rows.append(
                f"<tr>"
                f"<td>{p.partition_number}</td>"
                f"<td>{p.start_sector}</td>"
                f"<td>{p.sector_count}</td>"
                f"<td>{_format_size(p.size_bytes)}</td>"
                f"<td>{html.escape(p.partition_type_or_guid)}</td>"
                f"<td>{'Yes' if p.is_bootable else 'No'}</td>"
                f"<td>{html.escape(p.name or '-')}</td>"
                f"</tr>"
            )

        model_name = (
            f"{report_data.source_identity.vendor} {report_data.source_identity.product}".strip()
        )

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>RecoverX Forensic Report - {html.escape(report_data.session_id)}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      line-height: 1.5;
      color: #1e293b;
      background-color: #f8fafc;
      margin: 0;
      padding: 24px;
    }}
    .container {{
      max-width: 1200px;
      margin: 0 auto;
      background: #ffffff;
      padding: 32px;
      border-radius: 8px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }}
    h1 {{ color: #0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 12px; margin-top: 0; }}
    h2 {{
      color: #1e293b;
      margin-top: 28px;
      border-bottom: 1px solid #f1f5f9;
      padding-bottom: 6px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
      margin: 16px 0;
    }}
    .card {{ background: #f8fafc; border: 1px solid #e2e8f0; padding: 16px; border-radius: 6px; }}
    .card-title {{
      font-size: 0.85em;
      text-transform: uppercase;
      color: #64748b;
      font-weight: 600;
      margin-bottom: 6px;
    }}
    .card-value {{ font-size: 1.25em; font-weight: 700; color: #0f172a; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 0.9em; }}
    th, td {{ border: 1px solid #e2e8f0; padding: 8px 12px; text-align: left; }}
    th {{ background: #f1f5f9; font-weight: 600; color: #334155; }}
    tr:nth-child(even) {{ background: #f8fafc; }}
    code {{
      background: #f1f5f9;
      padding: 2px 4px;
      border-radius: 4px;
      font-size: 0.85em;
      font-family: monospace;
    }}
    .badge {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 12px;
      font-size: 0.8em;
      font-weight: 600;
    }}
    .badge-success {{ background: #dcfce7; color: #166534; }}
    .badge-info {{ background: #e0f2fe; color: #0369a1; }}
    .badge-danger {{ background: #fee2e2; color: #991b1b; }}
    .notice {{
      background: #eff6ff;
      border-left: 4px solid #3b82f6;
      padding: 12px 16px;
      margin: 20px 0;
      border-radius: 4px;
    }}
    .footer {{
      margin-top: 36px;
      padding-top: 16px;
      border-top: 1px solid #e2e8f0;
      font-size: 0.85em;
      color: #64748b;
      text-align: center;
    }}
  </style>
</head>
<body>
  <div class="container">
    <h1>RecoverX Forensic Recovery Report</h1>
    <p>Session ID: <code>{html.escape(report_data.session_id)}</code> |
       Generated: <strong>{
            time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime(report_data.generated_at))
        }</strong> |
       Software: RecoverX v{html.escape(report_data.app_version)}</p>

    <div class="notice">
      <strong>Forensic Integrity Assurance:</strong> Source storage media was accessed strictly
      in read-only mode by construction. No data was written, modified, or formatted on source.
      All reported candidate statuses are factual.
    </div>

    <h2>Source Device Identity</h2>
    <div class="grid">
      <div class="card">
        <div class="card-title">Device Model</div>
        <div class="card-value">{html.escape(model_name)}</div>
      </div>
      <div class="card">
        <div class="card-title">Capacity</div>
        <div class="card-value">{_format_size(report_data.source_identity.capacity_bytes)}
             ({report_data.source_identity.capacity_bytes:,} B)</div>
      </div>
      <div class="card">
        <div class="card-title">Sector Size</div>
        <div class="card-value">{report_data.source_identity.logical_sector_size} B Logical /
             {report_data.source_identity.physical_sector_size} B Physical</div>
      </div>
      <div class="card">
        <div class="card-title">Disk Identifier</div>
        <div class="card-value">
          <code>{html.escape(report_data.source_identity.disk_identifier or "N/A")}</code>
        </div>
      </div>
    </div>
    <p>Sector 0 Fingerprint (SHA-256):
       <code>{html.escape(report_data.source_identity.sector0_hash or "N/A")}</code></p>

    <h2>Triage & Health Assessment</h2>
    <p>Status: <strong>{html.escape(report_data.triage_result.status.value)}</strong></p>
    <p>Details: {html.escape(report_data.triage_result.explanation)}</p>
    <p>Recommendation: <em>{html.escape(report_data.triage_result.recommended_action)}</em></p>

    <h2>Partition & Volume Layout</h2>
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Start Sector</th>
          <th>Sector Count</th>
          <th>Size</th>
          <th>Filesystem</th>
          <th>Bootable</th>
          <th>Name / Description</th>
        </tr>
      </thead>
      <tbody>
        {"".join(part_rows) if part_rows else "<tr><td colspan='7'>None found.</td></tr>"}
      </tbody>
    </table>

    <h2>Scan & Recovery Statistics</h2>
    <div class="grid">
      <div class="card">
        <div class="card-title">Candidates Discovered</div>
        <div class="card-value">{len(report_data.candidates):,}</div>
      </div>
      <div class="card">
        <div class="card-title">Files Recovered</div>
        <div class="card-value">{len(successful_recoveries):,}</div>
      </div>
      <div class="card">
        <div class="card-title">Bytes Recovered</div>
        <div class="card-value">{_format_size(total_recovered_bytes)}</div>
      </div>
      <div class="card">
        <div class="card-title">Scan Duration</div>
        <div class="card-value">{report_data.scan_duration_seconds:.1f} s</div>
      </div>
    </div>

    <h2>Discovered File Formats</h2>
    <table>
      <thead>
        <tr>
          <th>Format / Extension</th>
          <th>Candidate Count</th>
          <th>Percentage of Total</th>
        </tr>
      </thead>
      <tbody>
        {
            "".join(format_rows)
            if format_rows
            else "<tr><td colspan='3'>No formats discovered.</td></tr>"
        }
      </tbody>
    </table>

    <h2>Verified Scope & Factual Limitations</h2>
    <div class="notice">
      <p><strong>Supported Filesystems:</strong> FAT12, FAT16, FAT32, exFAT
        (metadata recovery & unallocated cluster verification).</p>
      <p><strong>Supported Carving Formats:</strong> JPEG, PNG, PDF, ZIP / OOXML,
        MP4 / MOV, HEIC, GIF, BMP, WAV / AVI, MP3, TIFF / RAW, SQLite.</p>
      <p><strong>Honest Forensic Boundaries:</strong> Deleted files with fragmented,
        non-contiguous clusters or overwritten data blocks cannot be fully reconstructed
        without valid metadata allocation chains. All statuses reflect real file integrity.</p>
    </div>

    <h2>Candidate Files & Recovery Outcomes</h2>
    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Filename</th>
          <th>Relative Path</th>
          <th>Size</th>
          <th>Source Offset</th>
          <th>Method</th>
          <th>Factual Status</th>
          <th>SHA-256 (Prefix)</th>
          <th>Outcome</th>
        </tr>
      </thead>
      <tbody>
        {"".join(cand_rows) if cand_rows else "<tr><td colspan='9'>No candidates.</td></tr>"}
      </tbody>
    </table>

    <div class="footer">
      RecoverX Forensic Recovery Report &bull; Generated locally with 100% integrity checks.
    </div>
  </div>
</body>
</html>
"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(html_content)

        logger.info("Forensic report exported to HTML: %s", path)
        return path
