"""Concurrency-safe helpers for Manufacturing JSON state files."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


_STATE_FILE_LOCK = threading.RLock()


@contextmanager
def locked_state_file() -> Iterator[None]:
    """Serialize state-file read/modify/write cycles inside the web process."""
    with _STATE_FILE_LOCK:
        yield


def atomic_write_json(path: Path, payload: object) -> None:
    """Atomically replace a JSON file without exposing a partial document."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            json.dump(payload, temporary, ensure_ascii=False, indent=2)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
    finally:
        if temporary_name:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass
