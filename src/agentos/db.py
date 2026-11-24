"""SQLite storage: connections, migrations, transactions, backup and restore."""

import json
import sqlite3
from contextlib import contextmanager
from importlib import resources
from pathlib import Path

from agentos import paths
from agentos.errors import IntegrityError, NotInitialized
from agentos.util import now_iso

SCHEMA_VERSION = 1


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = Path(path) if path else paths.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def _migration_files() -> list[tuple[int, str]]:
    files = []
    for entry in resources.files("agentos.migrations").iterdir():
        name = entry.name
        if name.endswith(".sql") and name[:4].isdigit():
            files.append((int(name[:4]), entry.read_text(encoding="utf-8")))
    return sorted(files)


def current_version(conn: sqlite3.Connection) -> int:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    if not exists:
        return 0
    row = conn.execute("SELECT max(version) FROM schema_migrations").fetchone()
    return row[0] or 0


def migrate(conn: sqlite3.Connection) -> int:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    have = current_version(conn)
    if have > SCHEMA_VERSION:
        raise IntegrityError(f"database schema v{have} is newer than this AgentOS (v{SCHEMA_VERSION})")
    for version, sql in _migration_files():
        if version <= have:
            continue
        try:
            conn.executescript(
                "BEGIN IMMEDIATE;\n"
                + sql
                + f"\nINSERT INTO schema_migrations VALUES ({version}, '{now_iso()}');\nCOMMIT;"
            )
        except sqlite3.Error:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
    return current_version(conn)


@contextmanager
def write_tx(conn: sqlite3.Connection):
    """Open an immediate write transaction. Nested use joins the outer transaction."""
    if conn.in_transaction:
        yield conn
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def require_initialized() -> sqlite3.Connection:
    if not paths.db_path().exists():
        raise NotInitialized("AgentOS is not initialized. Run: agentos init")
    conn = connect()
    migrate(conn)
    return conn


def get_setting(conn: sqlite3.Connection, key: str, default=None):
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def put_setting(conn: sqlite3.Connection, key: str, value) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value)),
    )


def _stamp() -> str:
    return now_iso().replace("-", "").replace(":", "").rstrip("Z")


def _unique(path: Path) -> Path:
    candidate, n = path, 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}-{n}{path.suffix}")
        n += 1
    return candidate


def backup(conn: sqlite3.Connection, dest_dir: Path | None = None, prefix: str = "agentos") -> Path:
    dest_dir = Path(dest_dir) if dest_dir else paths.backups_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = _unique(dest_dir / f"{prefix}-{_stamp()}.db")
    target = sqlite3.connect(str(dest))
    try:
        conn.backup(target)
    finally:
        target.close()
    return dest


def validate_backup(src: Path) -> int:
    """Return the schema version of a backup file, or raise IntegrityError."""
    src = Path(src)
    if not src.is_file():
        raise IntegrityError(f"backup file not found: {src}")
    try:
        probe = sqlite3.connect(src.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            result = probe.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise IntegrityError(f"backup failed integrity check: {result}")
            version = current_version(probe)
        finally:
            probe.close()
    except sqlite3.DatabaseError as exc:
        raise IntegrityError(f"not a valid AgentOS database: {exc}") from exc
    if version == 0:
        raise IntegrityError("not an AgentOS database (no schema_migrations table)")
    if version > SCHEMA_VERSION:
        raise IntegrityError(f"backup schema v{version} is newer than this AgentOS (v{SCHEMA_VERSION})")
    return version


def restore(src: Path) -> Path | None:
    """Replace the live database with `src`. Returns the safety copy of the old database."""
    validate_backup(src)
    live = paths.db_path()
    safety = None
    live_conn = connect(live)
    try:
        if current_version(live_conn) > 0:
            safety = backup(live_conn, prefix="pre-restore")
        source = sqlite3.connect(Path(src).resolve().as_uri() + "?mode=ro", uri=True)
        try:
            source.backup(live_conn)
        finally:
            source.close()
    finally:
        live_conn.close()
    return safety
