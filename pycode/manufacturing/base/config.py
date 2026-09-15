"""Shared runtime configuration for all Manufacturing views."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

_runtime_dir = REPO_ROOT / "runtime" / "gyartasi-papirok"


def configure_manufacturing(runtime_dir: Path) -> None:
    """Set the runtime folder used for manufacturing state and caches."""
    global _runtime_dir
    _runtime_dir = runtime_dir


def runtime_dir() -> Path:
    """Return the configured manufacturing runtime folder."""
    return _runtime_dir


def operation_runtime_dir(operation_key: object) -> Path:
    """Return the isolated runtime root for one Manufacturing operation."""
    clean_key = str(operation_key or "").strip().lower()
    allowed = {
        "korpusz_osszekeszites",
        "front_osszekeszites",
        "cnc_furas",
        "pantolas",
        "topfloor",
    }
    return _runtime_dir / clean_key if clean_key in allowed else _runtime_dir


def bundle_disk_cache_dir() -> Path:
    """Return the folder used for parsed manufacturing bundle cache files."""
    return _runtime_dir / "bundle-cache"
