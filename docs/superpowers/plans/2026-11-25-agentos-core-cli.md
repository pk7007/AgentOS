# AgentOS Slice 1 — Core + CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A tested Python package and `agentos` CLI that records and enforces task graphs, the agent roster and lifecycle, limits and budgets, approvals, project-scoped memory, a tamper-evident audit trail and handovers, plus generated host plugin files.

**Architecture:** The host session (Codex or adapter `cc`) does the reasoning and spawns native subagents. AgentOS is a local SQLite-backed ledger and policy engine that the host consults through the CLI. Core modules are pure functions over a `sqlite3.Connection`, and every state change appends an audit event in the same transaction. The CLI is a thin argparse layer.

**Tech Stack:** Python ≥3.11, pydantic v2, stdlib argparse/sqlite3/tomllib, pytest, pytest-cov, ruff.

**Spec:** `docs/superpowers/specs/2026-11-25-agentos-core-cli-design.md`

## Global Constraints

- Python `>=3.11`; the only runtime dependency is `pydantic>=2.7,<3`.
- Runtime state lives under `AGENTOS_HOME` (default `~/.agentos`) and never inside the repo.
- Default limits: max_concurrent=4, max_depth=2, max_retries=2, max_agents_per_task=12, max_paid_spend_usd=0.0, max_remediation_rounds=5. Effective limit = the stricter of the local and host values.
- No model API calls anywhere in the package.
- No vendor name of the second host anywhere in tracked paths or contents. Run the owner's vendor-name `git grep` (from their global rules, kept outside the repo) before every commit; it must print nothing. Commit messages carry no attribution trailers.
- Every state-changing core function calls `audit.append_event` inside the same `write_tx`.
- Exit codes: 0 ok, 2 usage/not initialized, 3 denied by policy, 4 not found, 5 integrity error.
- Every CLI command accepts `--json` (machine output on stdout) and `--actor` (default env `AGENTOS_ACTOR` or `"host"`).
- Usage numbers are labeled `"estimate"` unless reported by a host. Never invent them.
- PowerShell 5.1 compatible scripts (no `&&`, no ternary).

## Review Focus

1. Two host sessions admitting workers at the same moment → never more than `max_concurrent` active instances (multi-process test in Task 8).
2. The same repo opened as `C:\Users\X\Proj` vs `c:\users\x\proj\` → same project id (Task 4).
3. `restore` given a corrupt file, a non-SQLite file, or a DB with a newer schema version → refuse with exit 5 and leave the current DB untouched (Task 2).
4. Memory search with FTS syntax characters (`"foo`, `AND`, `*`, `-`) → no crash, literal match (Task 11).
5. Any command other than `init`/`doctor` before `agentos init` → message "AgentOS is not initialized. Run: agentos init" and exit 2 (Task 2).

---

## File Structure

```
pyproject.toml  requirements-lock.txt  LICENSE  README.md  .gitignore  .gitattributes
src/agentos/
  __init__.py          __version__ = "0.1.0"
  errors.py            AgentOSError hierarchy with exit codes
  util.py              now_iso, new_id, sha256_json
  paths.py             agentos_home, db_path, handovers_dir, backups_dir
  db.py                connect, migrate, write_tx, require_initialized, backup, restore
  migrations/0001_init.sql
  audit.py             append_event, verify_chain, list_events
  redact.py            redact(text) -> (text, count)
  projects.py          project_id_for, activate, deactivate, list_projects, require_active
  tasks.py             task DAG + task state machine
  complexity.py        score
  templates.py         versioned agent templates + status
  lifecycle.py         17-state agent-instance machine
  governance.py        owner confirmation, emergency stop, approvals, protected settings
  governor.py          limits, budgets, reservations
  admission.py         admit
  recruit.py           rank
  performance.py       record_eval, summary
  memory.py            layered memory + FTS
  handover.py          create, resume
  gen/__init__.py  gen/tomlw.py  gen/codex.py  gen/host.py
  cli/__init__.py      main(argv) -> int, parser wiring, output/exit handling
  cli/cmd_*.py         one module per command group
definitions/plugin.toml  definitions/agents/*.toml  definitions/skills/agentos/SKILL.md
plugins/codex/         (generated, committed)
scripts/install.ps1  scripts/uninstall.ps1
docs/LIMITATIONS.md  docs/HOST_PROFILE.md  reports/AUDIT.md
tests/conftest.py  tests/unit/  tests/integration/  tests/security/  tests/concurrency/  tests/live/
```

`tests/conftest.py` provides fixtures: `home` (tmp_path set as `AGENTOS_HOME` via monkeypatch), `conn` (connected and migrated), `project` (an activated project from a `git init`'d tmp dir), `owner` (an `OwnerConfirmation` built through `governance.confirm_owner` with injected tty=True and the right phrase), and `cli` (runs `agentos.cli.main([...])` capturing stdout/stderr and returning `(code, out, err)`).

---

### Task 1: Package scaffold and CLI skeleton

**Files:**
- Create: `pyproject.toml`, `requirements-lock.txt`, `LICENSE` (MIT, holder "pk7007"), `README.md` (stub: one paragraph + install placeholder), `.gitignore` (`__pycache__/`, `.venv/`, `*.egg-info/`, `.coverage`, `htmlcov/`, `.pytest_cache/`, `dist/`, `build/`), `.gitattributes` (`* text=auto eol=lf`, `*.ps1 text eol=crlf`)
- Create: `src/agentos/__init__.py`, `src/agentos/errors.py`, `src/agentos/util.py`, `src/agentos/cli/__init__.py`
- Test: `tests/unit/test_cli_skeleton.py`, `tests/conftest.py` (only `cli` fixture for now)

**Interfaces:**
- Produces: `agentos.__version__: str`; `errors.AgentOSError(message, exit_code=1)`, subclasses `UsageError`(2), `NotInitialized`(2), `PolicyDenied`(3, has `.reasons: list[str]`), `NotFound`(4), `IntegrityError`(5); `util.now_iso() -> str` (UTC, `Z` suffix, seconds precision); `util.new_id(prefix: str) -> str` → `f"{prefix}_{uuid4().hex[:12]}"`; `util.sha256_json(obj) -> str` (`json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=False)`); `cli.main(argv: list[str] | None = None) -> int`; `cli.register(subparsers)` pattern: each `cmd_*.py` exposes `register(subparsers) -> None` and sets `func(args, ctx) -> dict | list` on its parsers; `main` catches `AgentOSError` → prints `error: <message>` (and reasons) to stderr, returns `exit_code`; prints result as JSON when `--json` else a readable rendering.
- pyproject: `[project.scripts] agentos = "agentos.cli:main"`, package-data includes `migrations/*.sql`; dev extra: `pytest>=8`, `pytest-cov>=5`, `ruff>=0.6`; `[tool.pytest.ini_options] testpaths=["tests"]`, marker `live`; `addopts = "-m 'not live'"`.

- [ ] **Step 1: Write failing tests**

```python
def test_version_flag(cli):
    code, out, _ = cli(["--version"])
    assert code == 0 and "0.1.0" in out

def test_unknown_command_exit_2(cli):
    code, _, err = cli(["nope"])
    assert code == 2

def test_agentos_error_maps_exit_code():
    from agentos.errors import PolicyDenied
    e = PolicyDenied("no", reasons=["limit"])
    assert e.exit_code == 3 and e.reasons == ["limit"]
```

- [ ] **Step 2:** Run `python -m pytest tests/unit/test_cli_skeleton.py -v`. Expected: FAIL (import error).
- [ ] **Step 3:** Create `.venv` (`python -m venv .venv`), `.venv\Scripts\pip install -e .[dev]`, implement the files above. argparse exits by `SystemExit(2)` on bad usage; `main` catches `SystemExit` and returns its code.
- [ ] **Step 4:** Run tests. Expected: PASS. Run `.venv\Scripts\pip freeze --exclude-editable > requirements-lock.txt`.
- [ ] **Step 5:** Commit `chore: scaffold agentos package and CLI skeleton`.

---

### Task 2: Paths, database, migrations, init/doctor, backup/restore

**Files:**
- Create: `src/agentos/paths.py`, `src/agentos/db.py`, `src/agentos/migrations/0001_init.sql`, `src/agentos/cli/cmd_system.py`
- Test: `tests/unit/test_db.py`, `tests/integration/test_cli_system.py`

**Interfaces:**
- Produces: `paths.agentos_home() -> Path` (env `AGENTOS_HOME` else `Path.home()/".agentos"`); `paths.db_path()` = home/`state/agentos.db`; `paths.handovers_dir()`, `paths.backups_dir()`.
- `db.SCHEMA_VERSION: int = 1`; `db.connect(path: Path | None = None) -> sqlite3.Connection` (row_factory `sqlite3.Row`, `PRAGMA journal_mode=WAL`, `foreign_keys=ON`, `busy_timeout=10000`, `isolation_level=None`); `db.migrate(conn) -> int`; `db.write_tx(conn)` context manager (`BEGIN IMMEDIATE`, commit, rollback on exception); `db.require_initialized() -> sqlite3.Connection` raises `NotInitialized("AgentOS is not initialized. Run: agentos init")` if the db file is missing; `db.backup(conn, dest_dir: Path | None = None) -> Path` (SQLite online backup to `backups/agentos-<UTC yyyymmddTHHMMSS>.db`); `db.restore(src: Path) -> Path` returns the path of the safety copy of the old DB.
- `0001_init.sql` creates all tables for slice 1: `schema_migrations(version, applied_at)`, `settings(key PK, value TEXT JSON)`, `projects(id PK, path, name, active INT, activated_at)`, `tasks(id PK, project_id FK, parent_id, title, objective, capabilities JSON, acceptance JSON, priority INT, risk, state, retries INT, max_retries INT, depth INT, created_at, updated_at)`, `task_deps(task_id, depends_on, PK both)`, `agent_templates(id, version, status, body JSON, created_at, PK(id,version))`, `agent_instances(id PK, template_id, template_version, project_id, task_id, parent_id, depth INT, host, state, termination_confirmed INT NULL, created_at, updated_at, last_reason)`, `evaluations(id PK, instance_id, template_id, evaluator_id, category, scores JSON, weighted REAL, evidence JSON, flags JSON, external_cause INT, created_at)`, `budgets(scope, scope_id, kind, limit_value REAL, PK(scope,scope_id,kind))`, `reservations(id PK, scope, scope_id, kind, amount REAL, actual REAL NULL, holder, state, created_at)`, `approvals(id PK, action, params_hash, params JSON, requested_by, status, created_at, expires_at, granted_at, consumed_at)`, `memory(id PK, project_id NULL, scope, layer, content, content_hash, source, author, confidence REAL, validated INT, version INT, supersedes NULL, deleted INT, tags JSON, created_at)`, `memory_fts` (FTS5 contentless-delete or external content on `memory.content`, kept in sync by triggers), `events(seq INTEGER PK AUTOINCREMENT, id, ts, kind, actor, project_id, payload JSON, prev_hash, hash)`, `handovers(id PK, project_id, host, created_at, path, resumed_by NULL, resumed_at NULL)`.
- `cmd_system.py`: `init` (creates dirs, migrates, idempotent, returns `{home, db, schema_version}`), `doctor` (checks: python version, db exists, integrity_check ok, schema version, audit chain ok, FTS5 available, `codex` on PATH; each `VERIFIED|UNSUPPORTED|UNKNOWN`; exit 0 even with warnings, 5 if integrity fails), `status` (counts by state, emergency stop flag), `backup`, `restore <file>` (owner-only, wired in Task 9; in this task it calls `db.restore` directly and Task 9 adds the guard).

- [ ] **Step 1: Write failing tests**

```python
def test_migrate_idempotent(home):
    from agentos import db
    c = db.connect(); assert db.migrate(c) == 1; assert db.migrate(c) == 1

def test_write_tx_rolls_back(conn):
    from agentos import db
    with pytest.raises(RuntimeError):
        with db.write_tx(conn):
            conn.execute("INSERT INTO settings VALUES ('k','1')"); raise RuntimeError
    assert conn.execute("SELECT count(*) FROM settings WHERE key='k'").fetchone()[0] == 0

def test_command_before_init_exits_2(cli, home):
    code, _, err = cli(["status"])
    assert code == 2 and "agentos init" in err

def test_backup_then_restore_roundtrip(cli, home): ...   # init, write a setting, backup, change it, restore, value is back
def test_restore_rejects_non_sqlite(cli, home, tmp_path): # file b"not a db" → exit 5, original db unchanged (compare sha256)
def test_restore_rejects_newer_schema(cli, home, tmp_path): # backup with schema_migrations version 99 → exit 5
def test_doctor_reports_statuses(cli, home):               # after init: --json has checks list, every status in {"VERIFIED","UNSUPPORTED","UNKNOWN"}
```

- [ ] **Step 2:** Run `python -m pytest tests/unit/test_db.py tests/integration/test_cli_system.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement. `restore`: open src read-only, `PRAGMA integrity_check` must equal `ok`, max(schema_migrations.version) ≤ `SCHEMA_VERSION`, else `IntegrityError`. Copy the current DB to `backups/pre-restore-<ts>.db`, then use the SQLite backup API from src into the live DB.
- [ ] **Step 4:** Run tests. Expected: PASS.
- [ ] **Step 5:** Commit `feat: sqlite storage, migrations, init/doctor/status, backup and restore`.

---

### Task 3: Tamper-evident audit log and redaction

**Files:**
- Create: `src/agentos/audit.py`, `src/agentos/redact.py`, `src/agentos/cli/cmd_audit.py`
- Test: `tests/unit/test_audit.py`, `tests/security/test_redact.py`

**Interfaces:**
- Produces: `redact.redact(text: str) -> tuple[str, int]`. It replaces matches with `[REDACTED]` for these patterns: `sk-[A-Za-z0-9_-]{16,}`, `gh[pousr]_[A-Za-z0-9]{20,}`, `github_pat_[A-Za-z0-9_]{20,}`, `AKIA[0-9A-Z]{16}`, `xox[abprs]-[A-Za-z0-9-]{10,}`, `-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----`, and for `(?i)\b(password|passwd|secret|api[_-]?key|token)\b\s*[:=]\s*\S+` only the value part. `redact.redact_obj(obj) -> obj` recursively redacts strings in dict/list.
- `audit.GENESIS = "0"*64`; `audit.append_event(conn, kind: str, actor: str, payload: dict, project_id: str | None = None) -> str` — payload passed through `redact_obj`; `hash = sha256(prev_hash + sha256_json({id,ts,kind,actor,project_id,payload}))`; must be called inside an open transaction (assert `conn.in_transaction`). `audit.verify_chain(conn) -> VerifyResult` (pydantic: `ok: bool, checked: int, first_bad_seq: int | None`). `audit.list_events(conn, limit: int = 50, kind: str | None = None, project_id: str | None = None) -> list[dict]`.
- CLI: `audit verify` (exit 5 when not ok), `audit log [--kind] [--limit]`. `init` appends `system.init`.

- [ ] **Step 1: Write failing tests**

```python
def test_chain_verifies(conn): # 3 events appended in write_tx → verify ok, checked == 3 (+ init event if any)
def test_tamper_detected(conn):
    ...; conn.execute("UPDATE events SET payload='{\"x\":2}' WHERE seq=2")
    r = audit.verify_chain(conn); assert not r.ok and r.first_bad_seq == 2
def test_deleted_row_detected(conn): # delete seq 2 → not ok
def test_append_outside_tx_raises(conn)
def test_redacts_known_secrets():
    t, n = redact("key sk-abcdefghijklmnop1234 and password: hunter2")
    assert "sk-abc" not in t and "hunter2" not in t and n == 2
def test_audit_payload_is_redacted(conn) # payload {"note": "token=abc123"} stored without abc123
```

- [ ] **Step 2–4:** Run (FAIL) → implement → run (PASS): `python -m pytest tests/unit/test_audit.py tests/security/test_redact.py -v`.
- [ ] **Step 5:** Commit `feat: hash-chained audit log and secret redaction`.

---

### Task 4: Projects

**Files:**
- Create: `src/agentos/projects.py`, `src/agentos/cli/cmd_project.py`
- Test: `tests/unit/test_projects.py`; extend `tests/conftest.py` with `project` fixture

**Interfaces:**
- Produces: `Project` model (`id, path, name, active: bool, activated_at`); `projects.repo_root(path: Path) -> Path` (`git rev-parse --show-toplevel`, else the path itself); `projects.project_id_for(path: Path) -> str` = `"prj_" + sha256(os.path.normcase(str(repo_root(path).resolve())).rstrip("\\/"))[:16]`; `activate(conn, path: Path, actor: str) -> Project`; `deactivate(conn, project_id: str, actor: str) -> Project`; `list_projects(conn) -> list[Project]`; `get_project(conn, id) -> Project` (NotFound); `require_active(conn, project_id) -> Project` raises `PolicyDenied("project is not activated", reasons=["project_inactive"])`.
- CLI: `project activate [PATH]` (default cwd), `project deactivate [PATH]`, `project list`. Every other command that needs a project resolves it from `--project PATH|ID` (default cwd) via `resolve_project(conn, arg) -> Project` in `cli/__init__.py`.

- [ ] **Step 1: Write failing tests**

```python
def test_same_repo_different_spelling_same_id(tmp_path):
    p = tmp_path / "My Proj"; p.mkdir(); subprocess.run(["git","init","-q",str(p)])
    assert project_id_for(p) == project_id_for(Path(str(p).upper() + "\\"))  # Windows normcase
def test_subdir_maps_to_repo_root(tmp_path)
def test_require_active_denies_inactive(conn, tmp_path)
def test_activate_twice_is_idempotent_and_audited(conn, tmp_path)  # one project row, two events
```

- [ ] **Step 2–4:** Run → implement → run: `python -m pytest tests/unit/test_projects.py -v`.
- [ ] **Step 5:** Commit `feat: project activation and isolation keys`.

---

### Task 5: Task graph and complexity score

**Files:**
- Create: `src/agentos/tasks.py`, `src/agentos/complexity.py`, `src/agentos/cli/cmd_task.py`
- Test: `tests/unit/test_tasks.py`, `tests/unit/test_complexity.py`

**Interfaces:**
- Consumes: `projects.require_active`, `audit.append_event`, `db.write_tx`.
- Produces: `TaskState` enum `pending, running, blocked, done, failed, cancelled`; `TASK_TRANSITIONS = {pending:{running,blocked,cancelled}, running:{done,failed,blocked,cancelled}, blocked:{pending,cancelled}, failed:{pending,cancelled}, done:set(), cancelled:set()}`; `MAX_TASK_DEPTH = 5`; `Task` model mirrors the table.
- `add_task(conn, project_id, title: str, objective: str = "", capabilities: list[str] = [], acceptance: list[str] = [], parent_id: str | None = None, priority: int = 50, risk: Literal["low","medium","high","critical"] = "low", actor="host") -> Task` — depth = parent.depth+1; deny when depth > `MAX_TASK_DEPTH`; parent must be in the same project.
- `add_dependency(conn, task_id, depends_on, actor) -> None` — deny self-dependency, cross-project, and any edge that creates a cycle (DFS from `depends_on` over existing edges reaching `task_id`).
- `ready_tasks(conn, project_id) -> list[Task]` — pending, with all deps `done`, ordered by priority desc then created_at.
- `set_state(conn, task_id, to: TaskState, actor, note: str | None = None) -> Task` — illegal transition → `PolicyDenied(reasons=["illegal_transition"])`; `pending→running` requires all deps done (`reasons=["dependencies_incomplete"]`); `failed→pending` increments `retries` and is denied with `retry_limit` when `retries >= max_retries` (max_retries comes from `governor.get_limits` once Task 8 exists; until then default 2 stored on the task).
- `get_task`, `list_tasks(conn, project_id, state=None)`.
- `complexity.ComplexityInput` (all ints ≥0: `task_count, dependency_depth, workstreams, files_touched`; 0–5: `domain_difficulty, uncertainty, risk, verification_effort`); `complexity.score(inp) -> ComplexityResult(score: int, band: str, suggested_agents: int, uncalibrated: bool = True)`. Weights (sum 100) on normalized factors capped at 1.0: task_count/20 ×15, dependency_depth/6 ×10, workstreams/6 ×15, files_touched/50 ×10, domain_difficulty/5 ×15, uncertainty/5 ×10, risk/5 ×15, verification_effort/5 ×10; `round()`. Bands: ≤15 `single`(1), ≤30 `small_team`(2), ≤50 `specialist_team`(3), ≤70 `multi_workstream`(4), ≤85 `department`(4), else `hierarchical`(4); then `suggested_agents = min(band_agents, max(1, workstreams))`.
- CLI: `task add TITLE [--objective] [--cap X]... [--accept X]... [--parent ID] [--priority N] [--risk R]`, `task dep TASK --on OTHER`, `task list [--state]`, `task inspect ID`, `task ready`, `task start|done|fail|block|cancel|retry ID [--note]`; `plan score --tasks N --depth N --workstreams N --files N --difficulty N --uncertainty N --risk N --verify N`.

- [ ] **Step 1: Write failing tests**

```python
def test_cycle_rejected(conn, project): a,b,c chain a<-b<-c; add_dependency(a, on=c) → PolicyDenied reasons contain "cycle"
def test_start_requires_deps_done(conn, project)
def test_ready_orders_by_priority(conn, project)
def test_retry_limit(conn, project): fail→retry twice ok, third → PolicyDenied "retry_limit"
def test_depth_limit(conn, project): chain of parents to depth 6 → PolicyDenied "max_task_depth"
def test_cross_project_dependency_denied(conn, project, other_project)
def test_trivial_task_is_single():
    r = score(ComplexityInput(task_count=1, dependency_depth=0, workstreams=1, files_touched=1,
              domain_difficulty=1, uncertainty=0, risk=0, verification_effort=1))
    assert r.band == "single" and r.suggested_agents == 1
def test_parallelism_caps_agents(): all factors max but workstreams=1 → band "hierarchical", suggested_agents == 1
def test_max_score_is_100(): all factors at cap → score == 100
```

- [ ] **Step 2–4:** Run → implement → run: `python -m pytest tests/unit/test_tasks.py tests/unit/test_complexity.py -v`.
- [ ] **Step 5:** Commit `feat: task DAG with cycle/depth/retry guards and complexity score`.

---

### Task 6: Agent templates

**Files:**
- Create: `src/agentos/templates.py`, `src/agentos/cli/cmd_template.py`, `definitions/agents/{lead,planner,implementer,reviewer,researcher,recovery}.toml`
- Test: `tests/unit/test_templates.py`

**Interfaces:**
- Produces: `TemplateStatus` enum `active, suspended, quarantined, retired`; `AgentTemplate` model: `id` (slug `^[a-z][a-z0-9-]{1,40}$`), `version: int`, `name, role, department, description: str`, `capabilities: list[str]`, `tools_allow: list[str] = []`, `tools_deny: list[str] = []`, `model_hint: str | None = None`, `reasoning_hint: Literal["low","medium","high"] | None = None`, `can_delegate: bool = False`, `security_class: Literal["standard","elevated"] = "standard"`, `read_only: bool = False`, `instructions: str`, `status: TemplateStatus = active`.
- `add_template(conn, t: AgentTemplate, actor) -> AgentTemplate` — new id → version 1; existing id → version = latest+1 (old rows kept, status unchanged).
- `get_template(conn, id, version: int | None = None) -> AgentTemplate` (latest when None); `list_templates(conn, status=None)` (latest version of each).
- `set_status(conn, id, to: TemplateStatus, actor, reason: str, owner: OwnerConfirmation | None = None) -> AgentTemplate`. Rules: active→suspended and any→quarantined need no owner; anything→retired, and quarantined|retired→active, require `owner` (else `PolicyDenied(reasons=["owner_required"])`); suspended→active needs no owner. Applies to all versions of the id. (`OwnerConfirmation` comes from Task 9. Until then, type it as `object | None` and tighten in Task 9.)
- `load_definitions(dir: Path) -> list[AgentTemplate]` reads `definitions/agents/*.toml` with `tomllib`.
- Definition files: `lead` (role "lead", can_delegate=true, caps `planning, delegation, integration`), `planner` (caps `planning, decomposition`), `implementer` (caps `python, implementation, testing`), `reviewer` (read_only=true, caps `review, security, testing`, reasoning_hint "high"), `researcher` (read_only=true, caps `research, analysis`), `recovery` (caps `debugging, recovery`). Each has 4–8 lines of instructions telling the agent to report evidence and never self-grade.
- CLI: `template add FILE.toml`, `template seed` (loads `definitions/agents`, skips identical bodies), `template list [--status]`, `template inspect ID [--version]`, `template suspend|quarantine ID --reason`, `template retire|reinstate ID --reason` (owner-gated in Task 9).

- [ ] **Step 1: Write failing tests**

```python
def test_versioning(conn): add twice with changed instructions → versions 1 and 2, get_template returns 2, get_template(version=1) still works
def test_retire_requires_owner(conn): set_status(..., retired, owner=None) → PolicyDenied "owner_required"
def test_quarantine_no_owner(conn)
def test_seed_definitions_load(conn): load_definitions(Path("definitions/agents")) → 6 templates, ids as listed
def test_bad_slug_rejected()
```

- [ ] **Step 2–4:** Run → implement → run: `python -m pytest tests/unit/test_templates.py -v`.
- [ ] **Step 5:** Commit `feat: versioned agent templates and seed definitions`.

---

### Task 7: Agent-instance lifecycle

**Files:**
- Create: `src/agentos/lifecycle.py`, `src/agentos/cli/cmd_agent.py` (transition/list/inspect only; `admit` added in Task 8)
- Test: `tests/unit/test_lifecycle.py`

**Interfaces:**
- Produces: `AgentState` enum with the 17 spec states (values upper-case strings). `TRANSITIONS: dict[AgentState, frozenset[AgentState]]`:
  PROPOSED→{RECRUITED,CANCELLED}; RECRUITED→{VALIDATING,CANCELLED}; VALIDATING→{AVAILABLE,FAILED,QUARANTINED}; AVAILABLE→{ASSIGNED,SUSPENDED,TERMINATED}; ASSIGNED→{RUNNING,CANCELLED,AVAILABLE}; RUNNING→{WAITING,BLOCKED,REVIEWING,COMPLETED,FAILED,CANCELLED,QUARANTINED}; WAITING→{RUNNING,CANCELLED,FAILED}; BLOCKED→{RUNNING,CANCELLED,FAILED}; REVIEWING→{COMPLETED,RUNNING,FAILED}; COMPLETED→{AVAILABLE,TERMINATED,ARCHIVED}; FAILED→{RETRAINING,TERMINATED,ASSIGNED}; RETRAINING→{VALIDATING,TERMINATED}; QUARANTINED→{SUSPENDED,TERMINATED}; SUSPENDED→{AVAILABLE,TERMINATED}; CANCELLED→{TERMINATED,ARCHIVED}; TERMINATED→{ARCHIVED}; ARCHIVED→{}.
  `ACTIVE_STATES = {ASSIGNED, RUNNING, WAITING, BLOCKED, REVIEWING}`.
- `AgentInstance` model mirrors the table. `can_transition(a, b) -> bool`; `transition(conn, instance_id, to: AgentState, actor, reason: str | None = None, runtime_confirmed: bool | None = None) -> AgentInstance` — illegal → `PolicyDenied(reasons=["illegal_transition"])` plus audit event `agent.transition_denied`. When `to == TERMINATED`, store `termination_confirmed = 1 if runtime_confirmed else 0`; rendering shows "TERMINATED (unconfirmed)" when 0. When leaving `ACTIVE_STATES` for a non-active state, call the release hook `governor.release_for_instance(conn, instance_id)`. Add it as a no-op stub in `governor.py` now; Task 8 fills it in.
- `get_instance`, `list_instances(conn, project_id=None, state=None, active_only=False)`, `active_count(conn) -> int` (global, across projects and hosts).
- CLI: `agent transition ID STATE [--reason] [--confirmed]`, `agent list [--active]`, `agent inspect ID`.

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.parametrize("a,b", [(a, b) for a in AgentState for b in TRANSITIONS[a]])
def test_all_legal_transitions_allowed(a, b): assert can_transition(a, b)
def test_illegal_count(): legal = sum(len(v) for v in TRANSITIONS.values()); every other pair is rejected by can_transition (17*17 - legal pairs)
def test_archived_is_terminal()
def test_terminate_unconfirmed_is_recorded(conn, instance)  # instance fixture inserts a row in RUNNING directly
def test_illegal_transition_audited(conn, instance)
```

- [ ] **Step 2–4:** Run → implement → run: `python -m pytest tests/unit/test_lifecycle.py -v`.
- [ ] **Step 5:** Commit `feat: agent instance lifecycle state machine`.

---

### Task 8: Limits, budgets, reservations and admission

**Files:**
- Create: `src/agentos/governor.py`, `src/agentos/admission.py`, `src/agentos/cli/cmd_budget.py`; modify `src/agentos/cli/cmd_agent.py` (add `admit`), `src/agentos/tasks.py` (read `max_retries` from limits)
- Test: `tests/unit/test_governor.py`, `tests/unit/test_admission.py`, `tests/concurrency/test_parallel_admission.py`

**Interfaces:**
- Consumes: `lifecycle.ACTIVE_STATES/active_count`, `templates.get_template`, `projects.require_active`, `tasks.get_task`, `governance.is_stopped`. Add `is_stopped(conn) -> bool` reading setting `governance.emergency_stop` in `governance.py` now; Task 9 adds the rest.
- `Limits` model with the Global Constraints defaults. `governor.get_limits(conn) -> Limits` = local values from settings `limits.<field>` merged with host values from settings `host.<host>.<field>` (minimum across all hosts recorded), each field = min(local, host) when host value present. `governor.set_limit(conn, field, value, actor, owner=None)` — lowering allowed without owner, raising requires owner (`owner_required`). `governor.set_host_limit(conn, host, field, value, actor)` — always allowed (it can only tighten).
- Budgets: `BudgetKind = Literal["agent_runs","tokens_est","usd"]`, `Scope = Literal["global","project","task"]`. `set_budget(conn, scope, scope_id, kind, limit, actor, owner=None)` — `kind == "usd"` with `limit > max_paid_spend_usd` requires owner. `reserve(conn, chain: list[tuple[Scope, str]], kind, amount: float, holder: str) -> str` — within the caller's `write_tx`, for each scope with a budget: used (actual of released, else amount of open) + amount must be ≤ limit, else `PolicyDenied(reasons=[f"budget_exceeded:{scope}:{kind}"])`. `kind == "usd"` and `amount > limits.max_paid_spend_usd` → `paid_spend_blocked`. `release(conn, reservation_id, actual: float | None = None)`; `release_for_instance(conn, instance_id)` releases open reservations whose holder == instance_id.
- `AdmitRequest(project_id, task_id, template_id, parent_instance_id: str | None = None, host: str)`; `AdmitDecision(allowed: bool, reasons: list[str], instance_id: str | None)`. `admission.admit(conn, req, actor) -> AdmitDecision` runs in one `write_tx` and collects **all** failing reasons (not just the first): `emergency_stop`, `project_inactive`, `task_not_found`, `task_not_open` (task not pending/running), `template_unavailable` (status ≠ active), `parent_not_active`, `parent_cannot_delegate`, `max_depth` (depth = parent.depth+1, root = 0, deny when > limits.max_depth), `max_concurrent` (active_count ≥ limit), `max_agents_per_task` (instances ever created for task ≥ limit), `duplicate` (same template_id+task_id already in ACTIVE_STATES), `budget_exceeded:*` (reserve 1 `agent_runs` on chain global/project/task). Allowed → insert instance in state ASSIGNED (admission compresses PROPOSED…AVAILABLE for active templates; event `agent.admitted` records this), holder of the reservation = instance id. Denied → event `agent.admission_denied` with reasons, returns decision (no exception). CLI `agent admit` exits 3 when denied and prints reasons.
- CLI: `agent admit --task ID --template ID [--parent ID] [--host codex|cc|other]`, `budget set SCOPE KIND LIMIT [--id]`, `budget show`, `limits show`, `limits set FIELD VALUE`, `limits host HOST FIELD VALUE`.

- [ ] **Step 1: Write failing tests**

```python
def test_admit_happy_path(conn, project, task, templates_seeded) → allowed, instance ASSIGNED, active_count == 1
def test_max_concurrent(conn, ...): 4 admits on 4 tasks ok, 5th → reasons include "max_concurrent"
def test_depth(conn, ...): lead(root) → child depth1 ok → grandchild depth2 ok → depth3 "max_depth"; child of non-delegating template → "parent_cannot_delegate"
def test_duplicate(conn, ...)
def test_all_reasons_collected(conn, ...): stopped + retired template → both reasons present
def test_release_on_completion(conn, ...): transition RUNNING→COMPLETED frees concurrency slot
def test_paid_spend_blocked(conn): reserve usd 0.01 → PolicyDenied "paid_spend_blocked"
def test_raise_limit_needs_owner(conn); test_lower_limit_ok(conn)
def test_host_limit_tightens(conn): set_host_limit("codex","max_concurrent",2) → get_limits().max_concurrent == 2
```

```python
# tests/concurrency/test_parallel_admission.py
def test_parallel_processes_never_exceed_limit(home, project_with_12_tasks):
    # 12 processes via multiprocessing (spawn), each opens its own connection and admits on a distinct task
    # assert exactly 4 allowed, 8 denied with "max_concurrent", and active_count == 4
```

- [ ] **Step 2–4:** Run → implement → run: `python -m pytest tests/unit/test_governor.py tests/unit/test_admission.py tests/concurrency -v`.
- [ ] **Step 5:** Commit `feat: limits, budgets, atomic reservations and worker admission`.

---

### Task 9: Governance — owner confirmation, emergency stop, approvals

**Files:**
- Modify/complete: `src/agentos/governance.py`; create `src/agentos/cli/cmd_governance.py`; wire owner guard into `template retire|reinstate`, `limits set` (raise), `budget set usd`, `restore`, `stop --lift`
- Test: `tests/unit/test_governance.py`, `tests/security/test_owner_guard.py`

**Interfaces:**
- `OwnerConfirmation` — frozen dataclass `(action: str, confirmed_at: str)` whose constructor requires a module-private sentinel. Only `confirm_owner` can build one.
- `confirm_owner(action: str, *, isatty: Callable[[], bool] = sys.stdin.isatty, prompt: Callable[[str], str] = input) -> OwnerConfirmation` — not a TTY → `PolicyDenied(reasons=["owner_confirmation_requires_terminal"])`; asks the owner to type exactly `I APPROVE <action>`; mismatch → `PolicyDenied(["owner_phrase_mismatch"])`. Environment variable `AGENTOS_OWNER_CONFIRM` is deliberately not supported.
- `emergency_stop(conn, actor, reason) -> None` (anyone may engage); `lift_stop(conn, actor, owner: OwnerConfirmation)`; `is_stopped(conn) -> bool`. While stopped, `admit` denies, but transitions of existing instances toward COMPLETED/FAILED/CANCELLED/TERMINATED/ARCHIVED/WAITING still work so work can wind down.
- `PROTECTED_PREFIXES = ("limits.", "governance.", "budget.usd")` and `set_setting(conn, key, value, actor, owner=None)` requires owner for protected keys except tightening via `governor`.
- Approvals: `request_approval(conn, action: str, params: dict, requested_by: str, ttl_minutes: int = 60) -> Approval` (status `pending`, `params_hash = sha256_json(params)`); `grant(conn, approval_id, owner: OwnerConfirmation, actor)`; `deny(conn, approval_id, actor)`; `check(conn, action, params) -> Approval | None` (granted, unexpired, unconsumed, exact hash match); `consume(conn, approval_id, actor)` (single use; second consume → `PolicyDenied(["approval_consumed"])`); `list_approvals(conn, status=None)`.
- CLI: `stop --reason R`, `stop --lift`, `approval request ACTION --params JSON`, `approval grant ID`, `approval deny ID`, `approval check ACTION --params JSON` (exit 3 when none), `approval consume ID`, `approval list`.

- [ ] **Step 1: Write failing tests**

```python
def test_non_tty_cannot_confirm(): confirm_owner("x", isatty=lambda: False) → PolicyDenied "owner_confirmation_requires_terminal"
def test_wrong_phrase(): prompt returns "yes" → PolicyDenied "owner_phrase_mismatch"
def test_cannot_forge_confirmation(): OwnerConfirmation("x", "t") → TypeError
def test_cli_retire_without_tty_denied(cli, home): subprocess (stdin=DEVNULL) `agentos template retire implementer --reason r` → exit 3
def test_stop_blocks_admission_but_allows_winddown(conn, ...)
def test_approval_bound_to_params(conn, owner): grant for {"branch":"main"}; check with {"branch":"dev"} → None
def test_approval_expires(conn, owner, monkeypatch now_iso)
def test_approval_single_use(conn, owner)
```

- [ ] **Step 2–4:** Run → implement → run: `python -m pytest tests/unit/test_governance.py tests/security/test_owner_guard.py -v`.
- [ ] **Step 5:** Commit `feat: owner confirmation, emergency stop and scoped approvals`.

---

### Task 10: Evaluations, performance and recruitment

**Files:**
- Create: `src/agentos/performance.py`, `src/agentos/recruit.py`, `src/agentos/cli/cmd_perf.py`
- Test: `tests/unit/test_performance.py`, `tests/unit/test_recruit.py`

**Interfaces:**
- `WEIGHTS = {"quality": .25, "accuracy": .20, "reliability": .15, "instruction_compliance": .10, "security_compliance": .10, "cost_efficiency": .08, "speed": .07, "collaboration": .05}`. `weighted(scores: dict[str, float]) -> float` — missing keys renormalize over present keys; every value must be 0–100.
- `record_eval(conn, instance_id, evaluator_id: str, category: str, scores: dict[str, float], evidence: list[str], flags: list[Literal["security_violation","integrity_violation"]] = [], external_cause: bool = False, actor="host") -> Evaluation` — rejects (`PolicyDenied`) `self_evaluation` when evaluator_id == instance_id or evaluator_id is the instance's parent or a descendant of it; `no_evidence` when evidence empty. Any flag → `templates.set_status(template, quarantined)` immediately and `lifecycle.transition(instance, QUARANTINED)` when that transition is legal.
- `summary(conn, template_id, category: str | None = None) -> PerfSummary` with `n` (excludes external_cause), `mean, recent_mean` (last 5), `stdev, confidence = min(n, 5) / 5, band, recommendation, consecutive_failures` (trailing evals with weighted < 50), `critical_count` (evals with any sub-score < 30, always shown), `excluded_external: int`. Bands: ≥95 `elite`, ≥85 `reliable`, ≥70 `monitor`, ≥50 `improve`, else `suspend_review`. Recommendation: n < 5 → `insufficient_evidence`; band `suspend_review` and ≥2 evals below 50 from ≥2 distinct evaluators → `retire_review`; band `improve` → `retrain`; else `retain`. Recommendations never change status on their own.
- `recruit.rank(conn, required: list[str], category: str | None = None, high_risk: bool = False) -> list[Candidate]`; `Candidate(template_id, version, score: float, match: float, reasons: list[str])`. match = |caps ∩ required| / |required|; score = .45·match + .25·(mean/100 if n else .5) + .15·(1 − failure_rate if n else .5) + .15·confidence. Excludes non-active templates and match == 0. `high_risk` also needs n ≥ 3 and mean ≥ 85. Sorted desc, ties by template_id. Empty list → CLI prints `capability gap: <missing caps>` (exit 0).
- CLI: `eval record INSTANCE --evaluator ID --category C --score key=val... --evidence REF... [--flag F] [--external]`, `perf show TEMPLATE [--category]`, `recruit --cap X... [--category C] [--high-risk]`.

- [ ] **Step 1: Write failing tests**

```python
def test_weights_sum_to_one(): assert abs(sum(WEIGHTS.values()) - 1) < 1e-9
def test_self_eval_rejected(conn, instance); test_parent_eval_rejected(conn, child_instance)
def test_no_evidence_rejected(conn, instance)
def test_security_flag_quarantines_template(conn, instance)
def test_insufficient_evidence_under_5(conn, ...)
def test_retire_review_needs_two_evaluators(conn, ...): 5 evals <50 all by one evaluator → "suspend_review" band but recommendation != "retire_review"
def test_external_cause_excluded(conn, ...)
def test_critical_visible_despite_high_mean(conn, ...): mean 90 but one security_compliance 10 → critical_count == 1
def test_rank_prefers_match_then_history(conn, seeded); test_high_risk_requires_proven(conn, seeded); test_gap_reported(cli, ...)
```

- [ ] **Step 2–4:** Run → implement → run: `python -m pytest tests/unit/test_performance.py tests/unit/test_recruit.py -v`.
- [ ] **Step 5:** Commit `feat: independent evaluations, performance summaries and recruitment ranking`.

---

### Task 11: Layered memory

**Files:**
- Create: `src/agentos/memory.py`, `src/agentos/cli/cmd_memory.py`
- Test: `tests/unit/test_memory.py`, `tests/security/test_memory_isolation.py`

**Interfaces:**
- `Layer` enum: `working, episodic, semantic, procedural, performance, failure, project, organizational, governance`. `MemoryRecord` mirrors the table.
- `add(conn, project_id: str | None, layer: Layer, content: str, source: str, author: str, confidence: float = 0.5, validated: bool = False, scope: Literal["project","org"] = "project", tags: list[str] = []) -> MemoryRecord` — content redacted first; `scope == "org"` requires `validated=True` and layer in {semantic, procedural, failure, organizational} else `PolicyDenied`; project scope requires an active project; dedupe on `content_hash = sha256(scope|project_id|layer|content)` among non-deleted records → returns the existing record; max content 20,000 chars (`UsageError`).
- `search(conn, project_id: str, query: str, layers: list[Layer] | None = None, include_org: bool = True, validated_only: bool = False, limit: int = 10) -> list[MemoryRecord]`. Build the FTS query by quoting each whitespace token as `"tok"` with inner quotes doubled, joined by spaces. Filter `deleted = 0 AND (project_id = ? OR (scope='org' AND ?include_org))`. Exclude superseded versions.
- `correct(conn, id, new_content, author) -> MemoryRecord` (new row version+1, `supersedes=id`); `delete(conn, id, actor)` (sets `deleted=1`, content → `""`, FTS row removed, audit event); `inspect(conn, id)`; `export(conn, project_id) -> list[dict]`.
- CLI: `memory add LAYER TEXT [--source] [--confidence] [--validated] [--org] [--tag]`, `memory search QUERY [--layer]... [--validated-only] [--no-org]`, `memory inspect ID`, `memory correct ID TEXT`, `memory delete ID`, `memory export [--out FILE]`.

- [ ] **Step 1: Write failing tests**

```python
def test_project_isolation(conn, project_a, project_b): add in A "deploy key rotation"; search from B → []
def test_org_visible_across_projects_only_when_validated(conn, a, b)
def test_unvalidated_org_rejected(conn, a)
def test_secret_redacted_on_write(conn, a)
@pytest.mark.parametrize("q", ['"foo', "AND", "*", "-x", "foo OR", "NEAR(", "'; DROP TABLE memory;--"])
def test_fts_special_chars_safe(conn, a, q): search does not raise
def test_correct_supersedes(conn, a): search returns only v2
def test_delete_wipes_content(conn, a)
def test_dedupe(conn, a)
```

- [ ] **Step 2–4:** Run → implement → run: `python -m pytest tests/unit/test_memory.py tests/security/test_memory_isolation.py -v`.
- [ ] **Step 5:** Commit `feat: layered project-scoped memory with provenance and FTS search`.

---

### Task 12: Handovers

**Files:**
- Create: `src/agentos/handover.py`, `src/agentos/cli/cmd_handover.py`
- Test: `tests/unit/test_handover.py`

**Interfaces:**
- `HANDOVER_ID_RE = r"^ho_[0-9a-f]{12}$"`. `Handover` model: `id, schema_version=1, project_id, host, created_at, objective, next_action, tasks: list[dict]` (id, title, state, deps), `active_instances: list[dict], pending_approvals: list[dict], decisions: list[dict]` (latest 10 memory records in layers project/governance), `git: {branch, head, dirty_files: list[str]}`, `limits: dict, budgets: dict`, `usage_note: "estimates only"`.
- `create(conn, project_id, repo_path: Path, host: str, objective: str, next_action: str, actor) -> Handover` — writes `handovers_dir()/<id>.json` (redacted via `redact_obj`) and a `handovers` row.
- `resume(conn, handover_id: str, repo_path: Path, host: str, actor) -> ResumeReport(ok: bool, warnings: list[str], handover: Handover)`. Steps: id must match the regex (`UsageError`). The file must resolve inside `handovers_dir()` (`IntegrityError`). Project id must equal `project_id_for(repo_path)` (`PolicyDenied project_mismatch`). The row must not already be resumed (`PolicyDenied already_resumed`): set `resumed_by/resumed_at` atomically with `UPDATE ... WHERE resumed_by IS NULL` and check rowcount. Warnings: `head_changed` (HEAD differs and recorded head is not an ancestor), `head_diverged`, `dirty_tree`, `orphaned_instances:<ids>` (instances still in ACTIVE_STATES from the handover).
- CLI: `handover create --objective TEXT --next TEXT [--host]` (prints id and path), `handover resume ID [--host]`, `handover list`.

- [ ] **Step 1: Write failing tests**

```python
def test_create_and_resume_cross_host(conn, project_repo): create(host="codex") → resume(host="cc") ok
def test_second_resume_denied(conn, project_repo)
def test_bad_id_rejected(conn, project_repo): resume("../../etc/passwd") → UsageError
def test_wrong_repo_denied(conn, project_repo, other_repo)
def test_head_changed_warning(conn, project_repo): new commit on unrelated orphan branch checked out → warning "head_diverged"
def test_secrets_not_in_handover_file(conn, project_repo)
```

- [ ] **Step 2–4:** Run → implement → run: `python -m pytest tests/unit/test_handover.py -v`.
- [ ] **Step 5:** Commit `feat: sanitized cross-host handovers with single-claim resume`.

---

### Task 13: Host plugin generators and the agentos skill

**Files:**
- Create: `definitions/plugin.toml` (`name="agentos"`, `version="0.1.0"`, `description`, `display_name="AgentOS"`), `definitions/skills/agentos/SKILL.md`, `src/agentos/gen/__init__.py`, `src/agentos/gen/tomlw.py`, `src/agentos/gen/codex.py`, `src/agentos/gen/host.py`, `src/agentos/cli/cmd_gen.py`, `docs/HOST_PROFILE.md`, generated `plugins/codex/**`
- Test: `tests/unit/test_gen.py`

**Interfaces:**
- `tomlw.dumps(data: dict) -> str` — supports nested tables (dict values), str (basic string with `\\`, `"`, control-char escapes; strings containing newlines use `"""` with backslashes and `"""` escaped), int, float, bool, list[str]. Round-trip test with `tomllib.loads`.
- `SKILL.md`: frontmatter `name: agentos`, `description:` one sentence saying when to use it (multi-step work in an activated project). Body: the host loop, `project activate` → `plan score` → `task add/dep` → `recruit` → `agent admit` **before** spawning any native subagent (if denied, do not spawn; report reasons) → after the subagent ends, `agent transition` and `eval record` by a different agent with evidence → `memory add` for validated lessons → `handover create` at session end. Rules: never fabricate results or usage, use `--json`, owner-only commands are for the human. ≤120 lines.
- `codex.generate(defs_dir: Path, out_dir: Path, force: bool = False) -> list[Path]` writes: `out/.codex-plugin/plugin.json` (`name, version, description, license "MIT", keywords, skills: "./skills/", interface: {displayName, shortDescription, category: "Coding", capabilities: ["Interactive","Read","Write"]}`), `out/skills/agentos/SKILL.md`, `out/agents/<id>.toml` (`developer_instructions`, `sandbox_mode = "read-only"` when `read_only`, `model_reasoning_effort` when `reasoning_hint`, `model` only when `model_hint`), `out/config-snippet.toml` (`[agents] max_threads = 4, max_depth = 2` + `[agents.<id>] description, config_file = "agents/<id>.toml"`), `out/.agents/plugins/marketplace.json` (`name "agentos"`, one plugin with `source {"source":"local","path":"./"}`, `policy {"installation":"AVAILABLE","authentication":"ON_INSTALL"}`, `category "Productivity"`).
- `host.generate(defs_dir: Path, profile_path: Path, out_dir: Path, force=False) -> list[Path]` — profile TOML keys: `manifest_dir`, `manifest_file`, `instructions_file`, `agents_dir`, `skills_dir`. Writes manifest JSON (`name, version, description`), `agents_dir/<id>.md` with YAML frontmatter (`name`, `description`, `tools` = comma-joined `tools_allow` when non-empty) + instructions body, the skill copied to `skills_dir/agentos/SKILL.md`, and `instructions_file` with a 10-line pointer to the skill and `agentos doctor`. Neither the profile values nor the vendor name appear in package source.
- Both generators keep `out/.agentos-gen.json` = `{relative_path: sha256}`. On regenerate, a file whose current hash ≠ recorded hash (edited by a person) is skipped and listed in the result as `skipped_modified` unless `force`.
- CLI: `gen codex [--out DIR] [--force]` (default `plugins/codex`), `gen host --profile FILE --out DIR [--force]`.
- `docs/HOST_PROFILE.md` explains the profile keys in neutral terms.
- Locally only (not committed; covered by `.git/info/exclude`): write `hosts/cc.local.toml` with the second host's real names, run `gen host` into `out/cc/`, and load it in that host to confirm it is recognized. Record the result in the audit report as VERIFIED or BLOCKED.

- [ ] **Step 1: Write failing tests**

```python
def test_tomlw_roundtrip(): data with nested tables, multiline instructions containing \"\"\" and backslashes → tomllib.loads(dumps(d)) == d
def test_codex_generate_files(tmp_path): expected file set exists; plugin.json loads and has skills "./skills/"; agents/reviewer.toml has sandbox_mode "read-only"
def test_codex_snippet_limits(tmp_path): tomllib: agents.max_threads == 4 and max_depth == 2
def test_generator_preserves_human_edits(tmp_path): edit agents/lead.toml → regenerate → file unchanged and listed in skipped_modified; --force overwrites
def test_host_generate_uses_profile(tmp_path): neutral profile (manifest_dir=".hostx") → files land under the profile names
def test_no_vendor_names_in_package():
    for p in Path("src").rglob("*"): ... assert no case-insensitive match of the two vendor words (build the words from the test's own constants, e.g. "cla" + "ude", so the test file itself stays clean)
```

- [ ] **Step 2–4:** Run → implement → run: `python -m pytest tests/unit/test_gen.py -v`. Then `agentos gen codex` to refresh `plugins/codex/`.
- [ ] **Step 5:** Commit `feat: codex plugin and profile-driven host generators with agentos skill`.

---

### Task 14: Installer, docs, audit report and live smoke test

**Files:**
- Create: `scripts/install.ps1`, `scripts/uninstall.ps1`, `docs/LIMITATIONS.md`, `reports/AUDIT.md`, `tests/live/test_codex_smoke.py`; rewrite `README.md`
- Test: `tests/integration/test_install_script.py`

**Interfaces:**
- `install.ps1 [-Apply] [-AgentosHome PATH]`: dry run by default and prints each planned action. With `-Apply`: checks `python --version` ≥3.11 (else exit 1 with message), creates `<home>\venv`, `pip install <repo>`, writes `<home>\bin\agentos.cmd` (`@"%~dp0..\venv\Scripts\agentos.exe" %*`), adds `<home>\bin` to the **user** PATH only when not present (prints old and new), runs `agentos init` and `agentos doctor`, prints the Codex plugin install commands without running them (`codex plugin marketplace add <repo>\plugins\codex`, then `codex plugin add agentos`). It never edits `~/.codex/config.toml`.
- `uninstall.ps1 [-Apply] [-PurgeState]`: removes venv, bin shim and the PATH entry. It keeps `state/`, `backups/` and `handovers/` unless `-PurgeState`, and backs up the DB first even then.
- `tests/integration/test_install_script.py`: runs `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install.ps1 -Apply -AgentosHome <tmp>` with `PATH` modification disabled via `-NoPath` switch (add it), then `<tmp>\bin\agentos.cmd doctor --json` exit 0; then uninstall `-Apply -NoPath` removes venv and keeps state. Skip when not Windows.
- `tests/live/test_codex_smoke.py` (`@pytest.mark.live`): in a temp git repo with an activated project and the generated plugin's skill copied to `.agents/skills/agentos/`, run `codex exec` with a prompt to use the agentos skill: activate, add one task, admit one `researcher`, transition it to COMPLETED. Assert the audit log contains `agent.admitted` and the chain verifies. Runs only with `-m live`.
- `docs/LIMITATIONS.md`: hosts can spawn without asking `admit` (hook enforcement in slice 2). Usage is estimates. A real terminal can satisfy owner confirmation. The complexity and recruit weights are uncalibrated. Native cancellation isn't verified, so TERMINATED can be "unconfirmed". The second host's live check depends on its CLI being on PATH.
- `reports/AUDIT.md`: table over spec §49 domains A–AO. Each row: criterion, score or `UNVERIFIED`/`BLOCKED`/`NOT APPLICABLE (slice N)`, evidence (test file::name or command), notes. Scores only where tests prove them. No average.
- `README.md`: what it is, the host-is-brain model, install, a 10-command quickstart, links to LIMITATIONS and AUDIT.

- [ ] **Step 1:** Write `test_install_script.py`. Run it, expected FAIL.
- [ ] **Step 2:** Implement scripts and run the test, expected PASS.
- [ ] **Step 3:** Full suite with coverage: `python -m pytest --cov=agentos --cov-branch --cov-report=term-missing`. Expected: all pass; ≥90% branch on `lifecycle, governor, admission, governance, audit`; ≥85% line overall. Add tests for real gaps before moving on.
- [ ] **Step 4:** `ruff check src tests` clean. Run the live test once with the owner's go-ahead: `python -m pytest -m live -v`. Record the result honestly in AUDIT.md.
- [ ] **Step 5:** Write LIMITATIONS, AUDIT, README. the vendor-name `git grep` prints nothing; `git status` shows no excluded files staged.
- [ ] **Step 6:** Commit `feat: installer, docs, audit report and live smoke test`.
