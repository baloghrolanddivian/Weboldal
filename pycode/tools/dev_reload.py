"""Development server reload supervision helpers."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


def dev_reload_token(env_name: str) -> str:
    """Return the current browser reload token."""
    return os.getenv(env_name, "dev-static")


def run_dev_supervisor(
    *,
    base_dir: Path,
    port: int,
    script_path: Path,
    child_env: str,
    reload_token_env: str,
    interval_seconds: float,
    watched_extensions: set[str],
    watched_files: set[str],
    ignored_dirs: set[str],
) -> None:
    """Run a child server process and restart it when watched files change."""

    def should_watch_path(path: Path) -> bool:
        """Provide should watch path behavior."""
        if any(part in ignored_dirs for part in path.parts):
            return False
        return path.suffix.lower() in watched_extensions or path.name in watched_files

    def build_watch_snapshot() -> dict[str, tuple[int, int]]:
        """Build build watch snapshot data."""
        snapshot: dict[str, tuple[int, int]] = {}
        for file_path in base_dir.rglob("*"):
            if not file_path.is_file():
                continue
            relative_path = file_path.relative_to(base_dir)
            if not should_watch_path(relative_path):
                continue
            stat = file_path.stat()
            snapshot[str(relative_path)] = (stat.st_mtime_ns, stat.st_size)
        return snapshot

    def spawn_child(reload_token: str) -> subprocess.Popen:
        """Provide spawn child behavior."""
        env = os.environ.copy()
        env[child_env] = "1"
        env[reload_token_env] = reload_token
        return subprocess.Popen([sys.executable, str(script_path)], cwd=base_dir, env=env)

    reload_counter = 0
    snapshot = build_watch_snapshot()
    child = spawn_child(f"reload-{reload_counter}")
    print(f"Dev reload supervisor active on http://localhost:{port}")

    try:
        while True:
            time.sleep(interval_seconds)
            next_snapshot = build_watch_snapshot()
            changed = next_snapshot != snapshot
            child_exited = child is not None and child.poll() is not None

            if not changed:
                if child is None:
                    continue
                if not child_exited:
                    continue
                print("A fejlesztoi szerver leallt. A kovetkezo modositasnal ujraindul.")
                child = None
                continue

            snapshot = next_snapshot
            reload_counter += 1
            print("Valtozas eszlelve, szerver ujrainditas...")

            if child and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)

            child = spawn_child(f"reload-{reload_counter}")
    except KeyboardInterrupt:
        print("\nFejlesztoi szerver leallitva.")
    finally:
        if child and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)

