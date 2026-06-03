"""Runtime configuration for the manufacturing papers workflow."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_runtime_dir = REPO_ROOT / "runtime" / "gyartasi-papirok"


def configure_manufacturing(runtime_dir: Path) -> None:
    """Configure configure manufacturing runtime settings."""
    global _runtime_dir
    _runtime_dir = runtime_dir


def runtime_dir() -> Path:
    """Provide runtime dir behavior."""
    return _runtime_dir


def bundle_disk_cache_dir() -> Path:
    """Provide bundle disk cache dir behavior."""
    return _runtime_dir / "bundle-cache"
