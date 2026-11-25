"""Owner authority: emergency stop (owner confirmation and approvals follow)."""

import sqlite3

from agentos import audit
from agentos.db import get_setting, put_setting, write_tx

STOP_KEY = "governance.emergency_stop"


def is_stopped(conn: sqlite3.Connection) -> bool:
    return bool(get_setting(conn, STOP_KEY, False))


def emergency_stop(conn: sqlite3.Connection, actor: str, reason: str) -> None:
    """Anyone may engage the stop. Only the owner may lift it."""
    with write_tx(conn):
        put_setting(conn, STOP_KEY, True)
        audit.append_event(conn, "governance.stop", actor, {"reason": reason})
