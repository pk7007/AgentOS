"""Structural rules that keep AgentOS small and safe: the core never imports the CLI, nothing opens a
network connection, the runtime dependency set is exactly what the docs say, every locked dependency is
pinned with hashes, and a populated database from the first release upgrades to the current schema."""

import ast
import re
import sqlite3
import tomllib
from pathlib import Path

from agentos import db, tasks

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "agentos"
NETWORK = {"socket", "ssl", "http", "urllib", "ftplib", "smtplib", "requests", "httpx", "aiohttp", "asyncio"}


def _imports(path: Path) -> set[str]:
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def _modules(exclude_cli: bool = False):
    for p in sorted(SRC.rglob("*.py")):
        if exclude_cli and "cli" in p.relative_to(SRC).parts:
            continue
        yield p


# the CLI reference generator renders `docs/CLI.md` from the parser itself; it is a build tool, not core
MAY_IMPORT_CLI = {"gen/clidocs.py"}


def test_the_core_never_imports_the_cli():
    offenders = {p.relative_to(SRC).as_posix(): sorted(m for m in _imports(p) if m.startswith("agentos.cli"))
                 for p in _modules(exclude_cli=True)}
    assert {k for k, v in offenders.items() if v} == MAY_IMPORT_CLI


def test_nothing_in_agentos_opens_a_network_connection():
    offenders = {p.relative_to(SRC).as_posix(): sorted(m for m in _imports(p) if m.split(".")[0] in NETWORK)
                 for p in _modules()}
    assert {k: v for k, v in offenders.items() if v} == {}


def test_the_runtime_dependencies_are_exactly_pydantic():
    meta = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert meta["dependencies"] == ["pydantic>=2.7,<3"]
    third_party = set()
    for p in _modules():
        for m in _imports(p):
            top = m.split(".")[0]
            if top not in {"agentos", "__future__"} and top not in __import__("sys").stdlib_module_names:
                third_party.add(top)
    assert third_party == {"pydantic"}


def test_every_locked_dependency_is_pinned_with_hashes():
    text = (ROOT / "requirements-lock.txt").read_text(encoding="utf-8")
    entries = [e for e in re.split(r"\n(?=\S)", text) if e.strip() and not e.startswith("#")]
    pins = {}
    for e in entries:
        name, _, version = e.split()[0].partition("==")
        assert version, f"{name} is not pinned with =="
        hashes = re.findall(r"--hash=sha256:([0-9a-f]{64})\b", e)
        assert hashes, f"{name} has no sha256 hash"
        pins[name.lower().replace("_", "-")] = version
    meta = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    wanted = meta["dependencies"] + meta["optional-dependencies"]["dev"]
    for req in wanted:
        name = re.split(r"[<>=!~\[ ]", req, maxsplit=1)[0].lower()
        assert name in pins, f"{name} from pyproject.toml is not in the lock"


def test_a_populated_first_release_database_upgrades_to_the_current_schema(tmp_path):
    conn = db.connect(tmp_path / "old.db")
    first = dict(db._migration_files())[1]
    conn.executescript("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);"
                       "BEGIN;" + first + "\nINSERT INTO schema_migrations VALUES (1, '2026-01-01T00:00:00Z');COMMIT;")
    conn.execute("INSERT INTO projects VALUES ('prj_old', 'C:/old', 'old', 1, '2026-01-01T00:00:00Z')")
    conn.execute("INSERT INTO tasks(id, project_id, title, created_at, updated_at) VALUES"
                 " ('task_old', 'prj_old', 'kept across upgrades', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    assert db.current_version(conn) == 1
    assert db.migrate(conn) == db.SCHEMA_VERSION
    kept = tasks.get_task(conn, "task_old")
    assert kept.title == "kept across upgrades" and kept.project_id == "prj_old"
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"messages", "claims", "workflows", "bench_runs"} <= tables
    versions = [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
    assert versions == list(range(1, db.SCHEMA_VERSION + 1))
    conn.close()


def test_a_failed_migration_leaves_the_earlier_ones_applied(tmp_path, monkeypatch):
    files = db._migration_files()
    broken = files[:2] + [(3, "CREATE TABLE broken (;")]
    monkeypatch.setattr(db, "_migration_files", lambda: broken)
    conn = db.connect(tmp_path / "half.db")
    try:
        db.migrate(conn)
    except sqlite3.Error:
        pass
    else:
        raise AssertionError("a broken migration must fail")
    assert db.current_version(conn) == 2 and not conn.in_transaction
    conn.close()


def test_one_version_everywhere_and_a_changed_skill_needs_a_new_version():
    import hashlib

    import agentos

    meta = tomllib.loads((ROOT / "definitions" / "plugin.toml").read_text(encoding="utf-8"))
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    manifest = __import__("json").loads((ROOT / "plugins" / "codex" / ".codex-plugin" / "plugin.json")
                                        .read_text(encoding="utf-8"))
    assert agentos.__version__ == project["version"] == meta["version"] == manifest["version"]
    skill = (ROOT / "definitions" / "skills" / "agentos" / "SKILL.md").read_text(encoding="utf-8")
    digest = hashlib.sha256(skill.replace("\r\n", "\n").encode()).hexdigest()
    assert digest == meta["skill_sha256"], (
        "the skill changed: bump the version in pyproject.toml, src/agentos/__init__.py and "
        "definitions/plugin.toml, set skill_sha256 to " + digest + ", then run agentos gen codex --force")


def test_the_structural_checks_catch_a_planted_violation(tmp_path):
    planted = tmp_path / "planted.py"
    planted.write_text("import socket\nfrom agentos.cli import main\nimport yaml\n", encoding="utf-8")
    found = _imports(planted)
    assert {"socket", "agentos.cli", "yaml"} <= found
    assert any(m.split(".")[0] in NETWORK for m in found)


def test_a_network_connection_in_a_test_is_refused():
    import socket

    s = socket.socket()
    try:
        with __import__("pytest").raises(AssertionError, match="network connection attempted"):
            s.connect(("127.0.0.1", 9))
    finally:
        s.close()
