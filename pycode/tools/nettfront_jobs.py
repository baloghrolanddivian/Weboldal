"""Storage helpers for legacy NettFront artifact jobs."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from nettfront.engine import create_bundle_zip


def is_valid_job_id(job_id: str) -> bool:
    """Return whether a job id uses the expected hex token shape."""
    return bool(re.fullmatch(r"[a-f0-9]{10,32}", job_id))


def nettfront_job_dir(runtime_dir: Path, job_id: str) -> Path | None:
    """Return the job directory for a valid job id."""
    if not is_valid_job_id(job_id):
        return None
    return runtime_dir / job_id


def write_nettfront_job(runtime_dir: Path, artifacts) -> tuple[str, dict]:
    """Persist legacy NettFront artifacts and metadata under runtime_dir."""
    job_id = uuid.uuid4().hex[:12]
    job_dir = runtime_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    (job_dir / "invoice-output.csv").write_bytes(artifacts.invoice_csv)
    (job_dir / "rendeles_sima.csv").write_bytes(artifacts.procurement_csv)
    if artifacts.compare_workbook is not None:
        (job_dir / "compare-output.xlsx").write_bytes(artifacts.compare_workbook)

    metadata = {
        "job_id": job_id,
        "invoice_row_count": len(artifacts.invoice_rows),
        "order_row_count": artifacts.order_row_count,
        "has_compare": artifacts.compare_workbook is not None,
        "missing_codes": artifacts.missing_codes,
    }
    (job_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    (job_dir / "nettfront-output.zip").write_bytes(create_bundle_zip(job_dir, include_compare=metadata["has_compare"]))
    return job_id, metadata


def read_nettfront_metadata(runtime_dir: Path, job_id: str) -> tuple[Path | None, dict | None]:
    """Read metadata for a persisted legacy NettFront job."""
    job_dir = nettfront_job_dir(runtime_dir, job_id)
    if job_dir is None or not job_dir.exists():
        return None, None

    metadata_path = job_dir / "metadata.json"
    if not metadata_path.exists():
        return None, None

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return job_dir, metadata


def nettfront_download_payload(runtime_dir: Path, job_id: str, artifact: str) -> tuple[bytes, str, str] | None:
    """Return file body, content type, and download name for a job artifact."""
    job_dir, metadata = read_nettfront_metadata(runtime_dir, job_id)
    if job_dir is None or metadata is None:
        return None

    artifact_map = {
        "invoice-csv": ("invoice-output.csv", "text/csv; charset=utf-8", "invoice-output.csv"),
        "procurement-csv": ("rendeles_sima.csv", "text/csv; charset=utf-8", "rendeles_sima.csv"),
        "bundle-zip": ("nettfront-output.zip", "application/zip", "nettfront-output.zip"),
    }

    if artifact == "compare-xlsx":
        if not metadata.get("has_compare"):
            return None
        file_path = job_dir / "compare-output.xlsx"
        if not file_path.exists():
            return None
        return (
            file_path.read_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "compare-output.xlsx",
        )

    config = artifact_map.get(artifact)
    if config is None:
        return None

    file_name, content_type, download_name = config
    file_path = job_dir / file_name
    if not file_path.exists():
        return None
    return file_path.read_bytes(), content_type, download_name

