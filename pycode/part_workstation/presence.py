"""Live assembly sessions; durable scan history belongs to the production XML."""

from __future__ import annotations

import re
import threading
import time

from .admin_store import mark_item_scanned
from .store import register_scan

PRESENCE_ROUTE = "/apps/alkatresz-munkalap/jelenlet"
ADMIN_SCANS_ROUTE = "/apps/alkatresz-munkalap/admin/beolvasasok"


class ScanPresence:
    TTL = 90

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.condition = threading.Condition(threading.RLock())
        self.sessions = {}
        self.history = {}
        self.revision = 0

    def _changed(self):
        self.revision += 1
        self.condition.notify_all()

    def _expire(self):
        for key, session in list(self.sessions.items()):
            if self.clock() - session["seen"] > self.TTL:
                del self.sessions[key]
                if session["item"]:
                    self._changed()

    @staticmethod
    def _validate(session_id, sequence):
        if not isinstance(session_id, str) or not re.fullmatch(r"[a-zA-Z0-9-]{16,80}", session_id):
            raise ValueError("Érvénytelen beolvasási munkamenet.")
        if type(sequence) is not int or not 0 <= sequence <= 9007199254740991:
            raise ValueError("Érvénytelen beolvasási sorszám.")

    def begin(self, session_id, sequence, user_id, user_name):
        self._validate(session_id, sequence)
        with self.condition:
            self._expire()
            previous = self.sessions.get(session_id)
            if previous and (previous["user_id"] != user_id or sequence <= previous["sequence"]):
                raise ValueError("Elavult beolvasási kérés.")
            session = dict(user_id=user_id, user_name=user_name, sequence=sequence,
                           seen=self.clock(), item=None)
            self.sessions[session_id] = session
            if previous and previous["item"]:
                self._changed()
            return session

    def activate(self, session_id, session, identity):
        # Disk I/O stays outside the presence lock; session identity prevents late
        # requests from reopening an item after another scan or a page close.
        item = mark_item_scanned(identity["production_id"], identity["con_id"], identity["oln_id"])
        with self.condition:
            key = (item["production_id"], item["con_id"], item["oln_id"])
            self.history[key] = item
            if self.sessions.get(session_id) is session:
                session.update(item=item, seen=self.clock())
            self._changed()
        return item

    def heartbeat(self, session_id, sequence, user_id):
        self._validate(session_id, sequence)
        with self.condition:
            self._expire()
            session = self.sessions.get(session_id)
            if not session or session["sequence"] != sequence or session["user_id"] != user_id:
                return False
            session["seen"] = self.clock()
            return bool(session["item"])

    def snapshot(self):
        with self.condition:
            self._expire()
            active = []
            for session in self.sessions.values():
                if session["item"]:
                    active.append({**session["item"], "user_name": session["user_name"]})
            return {"revision": self.revision, "active": active, "scanned": list(self.history.values())}

    def wait(self, revision, timeout=15):
        deadline = time.monotonic() + timeout
        with self.condition:
            while True:
                snapshot = self.snapshot()
                if snapshot["revision"] != revision or time.monotonic() >= deadline:
                    return snapshot
                self.condition.wait(min(1, max(0, deadline - time.monotonic())))


presence = ScanPresence()


def register_live_scan(barcode, *, session_id, sequence, user_id, user_name):
    session = presence.begin(session_id, sequence, user_id, user_name)
    state = register_scan(barcode)
    metadata = state["production_xml"]
    if metadata["lookup_status"] == "ready":
        identity = {"production_id": metadata["production_number"],
                    "con_id": metadata["fields"]["Barcode"], "oln_id": metadata["oln_id"]}
        state["scan_identity"] = presence.activate(session_id, session, identity)
    return state


def update_presence(payload, *, user_id, user_name):
    session_id, sequence = payload.get("session_id"), payload.get("sequence")
    action = payload.get("action")
    if action == "heartbeat":
        return {"present": presence.heartbeat(session_id, sequence, user_id)}
    if action not in {"open", "clear"}:
        raise ValueError("Érvénytelen jelenléti művelet.")
    identity = payload.get("identity")
    if action == "open" and (not isinstance(identity, dict)
                             or any(not isinstance(identity.get(key), str) for key in ("production_id", "con_id", "oln_id"))):
        raise ValueError("Érvénytelen tételazonosító.")
    session = presence.begin(session_id, sequence, user_id, user_name)
    if action == "open":
        presence.activate(session_id, session, identity)
    return {"present": action == "open"}
