"""Shared NettFront job storage helpers.

The functions in this module validate job identifiers, read persisted job
metadata, and serve generated artifacts from per-workflow runtime folders.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


def is_valid_job_id(job_id: str) -> bool:
    return bool(re.fullmatch(r"[a-f0-9]{10,32}", job_id))


def read_job(runtime_dir: Path, job_id: str) -> tuple[Path | None, dict | None]:
    if not is_valid_job_id(job_id):
        return None, None

    job_dir = runtime_dir / job_id
    if not job_dir.exists():
        return None, None

    metadata_path = job_dir / "metadata.json"
    if not metadata_path.exists():
        return None, None

    return job_dir, json.loads(metadata_path.read_text(encoding="utf-8"))


def download_payload(
    runtime_dir: Path,
    job_id: str,
    artifact: str,
    artifact_map: dict[str, tuple[str, str, str]],
) -> tuple[bytes, str, str] | None:
    job_dir, _metadata = read_job(runtime_dir, job_id)
    if job_dir is None:
        return None

    config = artifact_map.get(artifact)
    if config is None:
        return None

    file_name, content_type, download_name = config
    file_path = job_dir / file_name
    if not file_path.exists():
        return None
    return file_path.read_bytes(), content_type, download_name

