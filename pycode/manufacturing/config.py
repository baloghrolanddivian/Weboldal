"""Runtime configuration for the manufacturing papers workflow."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_runtime_dir = REPO_ROOT / "runtime" / "gyartasi-papirok"


def configure_manufacturing(runtime_dir: Path) -> None:
    """Set the runtime folder used for manufacturing state and caches."""
    global _runtime_dir
    _runtime_dir = runtime_dir


def runtime_dir() -> Path:
    """Return the configured manufacturing runtime folder."""
    return _runtime_dir


def bundle_disk_cache_dir() -> Path:
    """Return the folder used for parsed manufacturing bundle cache files."""
    return _runtime_dir / "bundle-cache"
