"""Owner authority: owner confirmation, emergency stop, scoped approvals, protected settings."""

import os
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from agentos import audit, util
from agentos.db import get_setting, put_setting, write_tx
from agentos.errors import NotFound, PolicyDenied

STOP_KEY = "governance.emergency_stop"
PROTECTED_PREFIXES = ("limits.", "governance.", "budget.usd")

_SENTINEL = object()


@dataclass(frozen=True)
class OwnerConfirmation:
    """Proof that the human owner confirmed one action at a real terminal. Only confirm_owner makes these."""

    action: str
    confirmed_at: str
    _token: object = field(repr=False, compare=False)

    def __post_init__(self):
        if self._token is not _SENTINEL:
            raise TypeError("OwnerConfirmation can only be created by governance.confirm_owner")


def _default_isatty() -> bool:
    """True only for a real interactive console. On Windows, NUL also reports isatty(), so ask the console API."""
    if sys.stdin is None or not sys.stdin.isatty():
        return False
    if os.name == "nt":
        import ctypes
        import msvcrt

        try:
            handle = msvcrt.get_osfhandle(sys.stdin.fileno())
        except (OSError, ValueError):
            return False
        mode = ctypes.c_uint32()
        return bool(ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)))
    return True


def _default_prompt(message: str) -> str:
    sys.stderr.write(message)
    sys.stderr.flush()
    return sys.stdin.readline()


def confirm_owner(action: str, *, isatty=None, prompt=None) -> OwnerConfirmation:
    """Ask the owner to type `I APPROVE <action>`. Agents run without a terminal, so they cannot confirm."""
    isatty = isatty or _default_isatty
    prompt = prompt or _default_prompt
    if not isatty():
        raise PolicyDenied("owner confirmation needs an interactive terminal",
                           reasons=["owner_confirmation_requires_terminal"])
    expected = f"I APPROVE {action}"
    answer = prompt(f"Owner confirmation for '{action}'. Type exactly: {expected}\n> ")
    if (answer or "").strip() != expected:
        raise PolicyDenied("owner confirmation phrase did not match", reasons=["owner_phrase_mismatch"])
    return OwnerConfirmation(action, util.now_iso(), _SENTINEL)


def is_owner(owner) -> bool:
    return isinstance(owner, OwnerConfirmation)


def require_owner(owner, what: str) -> None:
    if not is_owner(owner):
        raise PolicyDenied(f"{what} needs the owner", reasons=["owner_required"])


def is_stopped(conn: sqlite3.Connection) -> bool:
    return bool(get_setting(conn, STOP_KEY, False))


def emergency_stop(conn: sqlite3.Connection, actor: str, reason: str) -> None:
    """Anyone may engage the stop. Running work can still wind down; nothing new is admitted."""
    with write_tx(conn):
        put_setting(conn, STOP_KEY, True)
        audit.append_event(conn, "governance.stop", actor, {"reason": reason})


def lift_stop(conn: sqlite3.Connection, actor: str, owner) -> None:
    require_owner(owner, "lifting the emergency stop")
    with write_tx(conn):
        put_setting(conn, STOP_KEY, False)
        audit.append_event(conn, "governance.stop_lifted", actor, {"owner_action": owner.action})


def set_setting(conn: sqlite3.Connection, key: str, value, actor: str, owner=None) -> None:
    if key.startswith(PROTECTED_PREFIXES):
        require_owner(owner, f"changing protected setting {key}")
    with write_tx(conn):
        put_setting(conn, key, value)
        audit.append_event(conn, "settings.set", actor, {"key": key, "value": value})


class Approval(BaseModel):
    id: str
    action: str
    params_hash: str
    params: dict
    requested_by: str
    status: str
    created_at: str
    expires_at: str
    granted_at: str | None = None
    consumed_at: str | None = None


def _approval(row) -> Approval:
    import json

    return Approval(**(dict(row) | {"params": json.loads(row["params"])}))


def get_approval(conn: sqlite3.Connection, approval_id: str) -> Approval:
    row = conn.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
    if not row:
        raise NotFound(f"approval not found: {approval_id}")
    return _approval(row)


def request_approval(conn: sqlite3.Connection, action: str, params: dict, requested_by: str,
                     ttl_minutes: int = 60) -> Approval:
    import json

    aid, now = util.new_id("apr"), util.now_iso()
    expires = (datetime.now(UTC) + timedelta(minutes=ttl_minutes)).replace(microsecond=0)
    expires_iso = expires.isoformat().replace("+00:00", "Z")
    with write_tx(conn):
        conn.execute(
            "INSERT INTO approvals(id, action, params_hash, params, requested_by, status, created_at, expires_at) "
            "VALUES (?,?,?,?,?,'pending',?,?)",
            (aid, action, util.sha256_json(params), json.dumps(params), requested_by, now, expires_iso))
        audit.append_event(conn, "approval.requested", requested_by, {"approval_id": aid, "action": action,
                                                                       "params": params})
    return get_approval(conn, aid)


def grant(conn: sqlite3.Connection, approval_id: str, owner, actor: str) -> Approval:
    require_owner(owner, "granting an approval")
    with write_tx(conn):
        a = _pending(conn, approval_id)
        conn.execute("UPDATE approvals SET status='granted', granted_at=? WHERE id=?", (util.now_iso(), approval_id))
        audit.append_event(conn, "approval.granted", actor, {"approval_id": approval_id, "action": a.action})
    return get_approval(conn, approval_id)


def _pending(conn: sqlite3.Connection, approval_id: str) -> Approval:
    """Read inside the caller's write transaction, so the status can't change before the update."""
    a = get_approval(conn, approval_id)
    if a.status != "pending":
        raise PolicyDenied(f"approval is {a.status}", reasons=["approval_not_pending"])
    return a


def deny(conn: sqlite3.Connection, approval_id: str, actor: str) -> Approval:
    """Only a pending approval can be denied; otherwise nothing changes and nothing is audited."""
    with write_tx(conn):
        _pending(conn, approval_id)
        conn.execute("UPDATE approvals SET status='denied' WHERE id=?", (approval_id,))
        audit.append_event(conn, "approval.denied", actor, {"approval_id": approval_id})
    return get_approval(conn, approval_id)


def check(conn: sqlite3.Connection, action: str, params: dict) -> Approval | None:
    row = conn.execute(
        "SELECT * FROM approvals WHERE action=? AND params_hash=? AND status='granted' AND consumed_at IS NULL "
        "AND expires_at > ? ORDER BY created_at DESC LIMIT 1",
        (action, util.sha256_json(params), util.now_iso())).fetchone()
    return _approval(row) if row else None


def consume(conn: sqlite3.Connection, approval_id: str, actor: str) -> Approval:
    with write_tx(conn):
        a = get_approval(conn, approval_id)
        if a.consumed_at:
            raise PolicyDenied("approval was already used", reasons=["approval_consumed"])
        if a.status != "granted" or a.expires_at <= util.now_iso():
            raise PolicyDenied("approval is not granted or has expired", reasons=["approval_not_valid"])
        conn.execute("UPDATE approvals SET consumed_at=?, status='consumed' WHERE id=?", (util.now_iso(), approval_id))
        audit.append_event(conn, "approval.consumed", actor, {"approval_id": approval_id, "action": a.action})
    return get_approval(conn, approval_id)


def list_approvals(conn: sqlite3.Connection, status: str | None = None) -> list[Approval]:
    sql, params = "SELECT * FROM approvals", []
    if status:
        sql += " WHERE status=?"
        params.append(status)
    return [_approval(r) for r in conn.execute(sql + " ORDER BY created_at DESC", params)]
