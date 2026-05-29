"""Job persistence helpers for NettFront comparison runs.

This module writes comparison artifacts and metadata, reads completed jobs,
and maps downloadable artifact names to stored files.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from nettfront.engine import create_bundle_archive
from nettfront.tools.jobs import download_payload, read_job

from .config import compare_runtime_dir


def write_compare_job(artifacts) -> tuple[str, dict]:
    """Write compare job data."""
    job_id = uuid.uuid4().hex[:12]
    job_dir = compare_runtime_dir() / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    files = {
        "invoice-output.csv": artifacts.invoice_csv,
        "compare-output.xlsx": artifacts.compare_workbook,
    }
    metadata = {
        "job_id": job_id,
        "job_type": "compare",
        "bundle_name": "compare-output.zip",
        "invoice_row_count": len(artifacts.invoice_rows),
        "order_row_count": artifacts.order_row_count,
    }

    for file_name, payload in files.items():
        (job_dir / file_name).write_bytes(payload)

    (job_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    bundle_files = list(files.keys()) + ["metadata.json"]
    (job_dir / metadata["bundle_name"]).write_bytes(create_bundle_archive(job_dir, bundle_files))
    return job_id, metadata


def read_compare_job(job_id: str) -> tuple[Path | None, dict | None]:
    """Read compare job data."""
    return read_job(compare_runtime_dir(), job_id)


def compare_download_payload(job_id: str, artifact: str) -> tuple[bytes, str, str] | None:
    """Handle compare download payload logic for the NettFront workflows."""
    _job_dir, metadata = read_compare_job(job_id)
    if metadata is None:
        return None

    artifact_map = {
        "invoice-csv": ("invoice-output.csv", "text/csv; charset=utf-8", "invoice-output.csv"),
        "compare-xlsx": ("compare-output.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "compare-output.xlsx"),
        "bundle-zip": (metadata.get("bundle_name", "compare-output.zip"), "application/zip", metadata.get("bundle_name", "compare-output.zip")),
    }
    return download_payload(compare_runtime_dir(), job_id, artifact, artifact_map)
