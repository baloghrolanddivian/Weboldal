"""Runtime configuration for the manufacturing papers workflow."""

from __future__ import annotations

from pathlib import Path

_runtime_dir = Path("runtime") / "gyartasi-papirok"


def configure_manufacturing(runtime_dir: Path) -> None:
    global _runtime_dir
    _runtime_dir = runtime_dir


def runtime_dir() -> Path:
    return _runtime_dir


def bundle_disk_cache_dir() -> Path:
    return _runtime_dir / "bundle-cache"
