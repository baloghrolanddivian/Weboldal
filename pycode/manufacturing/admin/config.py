"""Admin-view import surface for shared Manufacturing configuration."""

# Admin configuration adapter inside the unified package.
from manufacturing.base.config import REPO_ROOT, bundle_disk_cache_dir, configure_manufacturing, runtime_dir

__all__ = ["REPO_ROOT", "bundle_disk_cache_dir", "configure_manufacturing", "runtime_dir"]
