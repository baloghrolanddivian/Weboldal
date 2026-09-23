"""TCP trigger client for the NettFront ICN camera reader."""

from __future__ import annotations

import os
import re
import socket
import threading


CAMERA_IP = os.getenv("NETTFRONT_CAMERA_IP", "192.168.2.40")
CAMERA_PORT = int(os.getenv("NETTFRONT_CAMERA_PORT", "9004"))
CAMERA_TIMEOUT_SECONDS = float(os.getenv("NETTFRONT_CAMERA_TIMEOUT", "10"))
CAMERA_TRIGGER = b"LON\r"
_CAMERA_LOCK = threading.Lock()


class CameraReadError(RuntimeError):
    """Raised when the camera cannot provide a usable ICN."""


class CameraBusyError(CameraReadError):
    """Raised when another request is already using the single camera."""


def trigger_camera_read() -> dict[str, str]:
    """Trigger one camera read and return its decoded ICN and raw response."""
    if not _CAMERA_LOCK.acquire(blocking=False):
        raise CameraBusyError("A kamera már egy másik beolvasást végez.")
    try:
        chunks: list[bytes] = []
        try:
            with socket.create_connection((CAMERA_IP, CAMERA_PORT), timeout=5) as connection:
                connection.sendall(CAMERA_TRIGGER)
                connection.settimeout(CAMERA_TIMEOUT_SECONDS)
                total_size = 0
                while True:
                    chunk = connection.recv(4096)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    total_size += len(chunk)
                    if b"\r" in chunk or total_size >= 64 * 1024:
                        break
        except socket.timeout as exc:
            raise CameraReadError("A kamera nem válaszolt 10 másodpercen belül.") from exc
        except OSError as exc:
            raise CameraReadError(f"A kamerakapcsolat nem sikerült: {exc}") from exc
        raw_bytes = b"".join(chunks)
        raw_text = raw_bytes.decode("utf-8", errors="replace").strip("\x00\r\n \t")
        matches = re.findall(r"(?<!\d)(\d{4,30})(?!\d)", raw_text)
        if not matches:
            raise CameraReadError(f"A kamera válasza nem tartalmaz érvényes ICN-t: {raw_text or '(üres válasz)'}")
        return {"icn": matches[-1], "raw": raw_text}
    finally:
        _CAMERA_LOCK.release()
