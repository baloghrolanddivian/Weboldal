"""Job persistence and artifact mapping for procurement runs.

The functions here store generated procurement bundles, update metadata, and
serve downloadable CSV, ZIP, and report artifacts.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from nettfront.engine import create_bundle_archive
from nettfront.tools.jobs import download_payload, read_job

from .config import procurement_runtime_dir


def read_procurement_job(job_id: str) -> tuple[Path | None, dict | None]:
    return read_job(procurement_runtime_dir(), job_id)


def procurement_download_payload(job_id: str, artifact: str) -> tuple[bytes, str, str] | None:
    _job_dir, metadata = read_procurement_job(job_id)
    if metadata is None:
        return None

    artifact_map = {
        "invoice-csv": ("invoice-output.csv", "text/csv; charset=utf-8", "invoice-output.csv"),
        "procurement-csv": ("rendeles_sima.csv", "text/csv; charset=utf-8", "rendeles_sima.csv"),
        "bundle-zip": (
            metadata.get("bundle_name", "procurement-output.zip"),
            "application/zip",
            metadata.get("bundle_name", "procurement-output.zip"),
        ),
    }
    return download_payload(procurement_runtime_dir(), job_id, artifact, artifact_map)

def persist_procurement_job(job_dir: Path, metadata: dict, artifacts, uploaded_parts_name: str = "", uploaded_parts_bytes: bytes | None = None) -> dict:
    (job_dir / "invoice-output.csv").write_bytes(artifacts.invoice_csv)
    (job_dir / "rendeles_sima.csv").write_bytes(artifacts.procurement_csv)

    updated_metadata = {
        **metadata,
        "invoice_row_count": len(artifacts.invoice_rows),
        "missing_codes": artifacts.missing_codes,
    }

    if uploaded_parts_name and uploaded_parts_bytes is not None:
        suffix = Path(uploaded_parts_name).suffix.lower() or ".xlsx"
        stored_name = f"alkatreszlista{suffix}"
        (job_dir / stored_name).write_bytes(uploaded_parts_bytes)
        updated_metadata["uploaded_parts_name"] = uploaded_parts_name
        updated_metadata["uploaded_parts_file"] = stored_name

    metadata_path = job_dir / "metadata.json"
    metadata_path.write_text(json.dumps(updated_metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    bundle_name = updated_metadata.get("bundle_name", "procurement-output.zip")
    bundle_files = ["invoice-output.csv", "rendeles_sima.csv", "metadata.json"]
    (job_dir / bundle_name).write_bytes(create_bundle_archive(job_dir, bundle_files))
    return updated_metadata


def write_procurement_job(
    artifacts,
    source_invoice_name: str,
    source_invoice_bytes: bytes,
    uploaded_parts_name: str = "",
    uploaded_parts_bytes: bytes | None = None,
) -> tuple[str, dict]:
    job_id = uuid.uuid4().hex[:12]
    job_dir = procurement_runtime_dir() / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    source_invoice_file = "source-invoice.pdf"
    (job_dir / source_invoice_file).write_bytes(source_invoice_bytes)

    metadata = {
        "job_id": job_id,
        "job_type": "procurement",
        "bundle_name": "procurement-output.zip",
        "source_invoice_name": source_invoice_name,
        "source_invoice_file": source_invoice_file,
    }
    metadata = persist_procurement_job(
        job_dir,
        metadata,
        artifacts,
        uploaded_parts_name=uploaded_parts_name,
        uploaded_parts_bytes=uploaded_parts_bytes,
    )
    return job_id, metadata
