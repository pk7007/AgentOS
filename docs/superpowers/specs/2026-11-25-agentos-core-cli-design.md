# AgentOS — Slice 1: Core + CLI — Design

Status: APPROVED by owner 2026-11-25
Date: 2026-11-25
Source spec: "AgentOS V4.0 — Universal Self-Evolving Corporate AI Operating System" (owner-supplied, kept local)

## 1. Intent and why

The owner wants a permanent layer over their coding hosts (Codex, plus a second host referred to here
as adapter `cc`). It should size up each task, bring in only the specialists it needs, track how each
agent configuration performs, retire the ones that keep failing, and improve over time through tested,
reversible changes. Money, permissions and risky actions stay under owner control.

The full spec is several projects. **Slice 1 builds the part every later slice depends on:** a tested
Python core and an `agentos` CLI that *records and enforces*: the task graph, the agent roster and its
lifecycle, scores, budgets and limits, approvals, project-scoped memory, an audit trail and handovers.
Plugins for both hosts are thin layers that teach the host to call this CLI.

Key architectural call: **the host session is the brain, AgentOS is the ledger and the referee.**
Codex or the `cc` host does the reasoning and spawns its own native subagents, using the owner's existing
subscription. AgentOS never calls a model API itself, so additional paid spend stays at zero by construction.
Before the host spawns or retires a worker, records a result or spends budget, it asks the CLI.
The CLI says yes or no and writes it down.

## 2. Goals, non-goals, anti-goals

Goals (slice 1)
- A Python package `agentos` with an `agentos` CLI, installed per user and usable across projects.
- Rules enforced in code, not just written into prompts: limits, lifecycle transitions, approvals, emergency stop,
  project isolation, append-only audit.
- Every rule has deterministic tests.
- A portable `agentos` skill (SKILL.md) and generated Codex plugin files, so a real Codex session can drive it.
- Honest criterion-level audit (`reports/AUDIT.md`) that marks later-slice items UNVERIFIED or BLOCKED.

Non-goals (later slices)
- Self-improvement experiments and champion/challenger promotion (slice 3).
- Benchmark suite comparing single-agent, fixed-team and dynamic setups (slice 3).
- Model routing registry, predictive staffing, automatic skill creation (slice 4).
- Hooks that block host actions without asking the CLI (slice 2).
- Dashboard (after slice 3). Persistent background service (needs separate owner approval).

Anti-goals: things that would count as failure even if the code works
- Fabricating anything: agents that never ran, test results, token counts, costs or scores.
- Any paid API call or new subscription.
- Touching global host config or unrelated repos without a dry run and owner approval.
- Pushing anything to GitHub that names the second host's vendor (owner's global rule).
- More agents for the sake of more agents.

## 3. Constraints

- Windows 11, PowerShell 5.1 (no `&&`), Python 3.11.3, git 2.45, gh 2.98, Node 26, Codex CLI 0.171.
- The `cc` host CLI is not on PATH, so live verification of the `cc` side is BLOCKED until it is.
- Codex facts verified on this machine: plugins (stable), hooks (stable), `multi_agent` on (deprecated flag),
  `multi_agent_v2` stable but off; plugin manifest at `.codex-plugin/plugin.json`; agent roles defined in
  `[agents.<name>]` with `config_file = "agents/<name>.toml"`, `[agents] max_threads / max_depth`.
- Owner rule: no vendor name of the second host in any pushed path or file content. Host-specific file and
  folder names for `cc` are therefore never in the repo. They come from a local, git-excluded host profile.
- Runtime state, memory and logs live in `~/.agentos/` (override `AGENTOS_HOME`), never in the repo.
- Hosts don't expose exact token usage to a script. Usage fields are recorded as `estimate` unless a host
  reports them, and labeled as such.

## 4. Approaches considered

| Approach | Trade-off | Decision |
|---|---|---|
| **A. Core + CLI first**, thin host layers | Real enforcement and tests first; usable in a session a bit later | **Chosen by owner** |
| B. Native plugin first (markdown agents/skills/hooks, small store) | Usable sooner; limits are only as strong as prompts | Rejected: spec requires real enforcement |
| C. Own orchestrator calling model APIs | Full control of agents | Rejected: paid spend, duplicates native subagents |

## 5. Design

### 5.1 Stack (my call)
- Python ≥3.11, `src/` layout, `pyproject.toml`.
- Runtime dependency: `pydantic` v2 only. CLI on stdlib `argparse` (no Typer/Click). Storage on stdlib `sqlite3`.
- Dev: `pytest`, `pytest-cov`, `ruff`. Versions pinned in a lock file (`requirements-lock.txt`).
- MIT license.

### 5.2 Storage
- One SQLite file `~/.agentos/state/agentos.db`, WAL mode, `foreign_keys=ON`, every write in a transaction
  (`BEGIN IMMEDIATE` for reservations so two agents can't oversubscribe).
- `schema_migrations` table and numbered migrations in `src/agentos/migrations/`.
- Tables: `projects`, `tasks`, `task_deps`, `agent_templates`, `agent_instances`, `assignments`,
  `evaluations`, `reservations`, `budgets`, `approvals`, `memory` (+ FTS5 index), `events`, `handovers`, `settings`.

### 5.3 Modules (`src/agentos/`)
| Module | Does |
|---|---|
| `schemas` | Pydantic models for every record and CLI JSON output |
| `db` | Connection, transactions, migrations, backup/restore via SQLite backup API |
| `projects` | Activate/deactivate a project (by git root path → stable id). Nothing runs in an inactive project |
| `tasks` | Task DAG: add, depend, cycle and missing-input detection, ready set, state changes, retry counts |
| `complexity` | 0–100 score from stated factors → staffing band (single / small team / … / hierarchical). Heuristic, labeled uncalibrated |
| `templates` | Versioned agent templates (role, department, capabilities, tools allow/deny, limits). Status active/suspended/retired |
| `lifecycle` | Agent-instance state machine (17 states from spec §17). Illegal transitions raise and are audited |
| `governor` | Limits and budgets: max concurrent 4, max depth 2, retries 2, agents per task 12, paid spend 0. Atomic reservations; strictest of local limit and host limit wins |
| `admission` | `admit` decision for a new worker: scope, parent authority, depth, concurrency, budget, duplicate check. Returns allow/deny + reasons |
| `recruit` | Rank templates for required capabilities: match, history, reliability, cost, security eligibility, evidence confidence |
| `performance` | Weighted score (spec §18 weights), per category, confidence from sample size. Policy bands produce *recommendations*; retire needs ≥5 comparable evaluations, quarantine is immediate for security/integrity flags |
| `governance` | Approvals bound to action + SHA-256 of parameters, with expiry. Emergency stop flag blocks all admissions. Protected settings change only with owner approval |
| `memory` | Layered records (working, episodic, semantic, procedural, performance, failure, project, organizational, governance) with provenance, confidence, validation status, project scope. Queries always scoped. Secret patterns redacted on write |
| `audit` | Append-only `events` with hash chain (`prev_hash`); `agentos audit verify` detects tampering |
| `handover` | Sanitized JSON handover (objective, task graph, decisions, branch, commit, files, tests, approvals, next action). Resume validates repo state and task ownership |
| `cli` | argparse front end. Every command supports `--json`. Meaningful exit codes (0 ok, 2 usage, 3 denied by policy, 4 not found, 5 integrity error) |

### 5.4 Owner-only actions
Approving, lifting emergency stop, changing protected limits, and retiring a template require an owner
confirmation: an interactive TTY and a typed confirmation phrase. Host agents run commands without a TTY,
so they can't confirm on the owner's behalf. Known limitation: anyone with a real terminal can confirm.
This is documented, not hidden.

### 5.5 CLI surface in slice 1
`init`, `doctor`, `status`, `stop` / `resume-all`,
`project activate|deactivate|list`,
`task add|dep|list|inspect|ready|start|done|fail|block`,
`plan score` (complexity),
`template add|list|inspect|suspend|retire|reinstate`,
`recruit` (rank templates for capabilities),
`agent admit|transition|list|inspect` (live instances),
`eval record`, `perf show`,
`budget set|show`, `approval request|grant|list`,
`memory add|search|inspect|correct|delete|export`,
`audit verify|log`,
`handover create|resume`,
`backup`, `restore`.
Deferred to later slices: `run`, `learn`, `experiments`, `benchmark`, `improve`, `sync`, `update`, `rollback`.

### 5.6 Host layers
- Canonical definitions in `definitions/` (YAML): agent templates (CEO/lead, planner, implementer, reviewer,
  researcher, recovery), the `agentos` skill, policies.
- `agentos gen codex` writes `.codex-plugin/plugin.json`, `skills/agentos/SKILL.md`, and Codex agent TOMLs
  plus an `[agents]` snippet, into the repo's `plugins/codex/` folder (committed) or a target dir.
- `agentos gen cc --profile <path>` writes the second host's plugin from the same definitions, using a
  local host profile (folder names, manifest file name, instruction file name). The profile and the
  generated output are git-excluded and never pushed.
- Generators refuse to overwrite files that changed since they last wrote them (content hash recorded) unless `--force`.
- The skill teaches the host loop: `project activate` → `plan score` → `task add` → `recruit` → `agent admit`
  before spawning a native subagent → `eval record` and `agent transition` after → `handover create` at the end.

### 5.7 Install
`scripts/install.ps1`: checks Python, creates `~/.agentos/venv`, `pip install` from the repo, creates a small
`agentos.cmd` shim in `~/.agentos/bin`, runs `agentos init` and `agentos doctor`. Dry-run by default (`-Apply`
to act). It prints the PATH change and only makes it with `-Apply`. No host config changes in slice 1:
installing the Codex plugin is a printed command the owner runs. `scripts/uninstall.ps1` removes the venv
and shim and keeps `state/` unless `-PurgeState`.

### 5.8 Tests and evidence
- `tests/unit`, `tests/integration` (CLI via subprocess against a temp `AGENTOS_HOME`), `tests/security`
  (redaction, path traversal in handover/restore, isolation, approval tampering), `tests/concurrency`
  (parallel reservations from multiple processes never exceed limits).
- Coverage: ≥90% branch on `lifecycle`, `governor`, `admission`, `governance`, `audit`; ≥85% line overall.
- One live smoke test: a real `codex exec` session in a scratch repo uses the skill to activate a project,
  admit one worker and record a result. It runs only when the owner passes `--live`. The result goes in the audit
  as VERIFIED or BLOCKED, never mocked.
- `reports/AUDIT.md`: criterion register (spec §49), each scored with evidence links. Items outside slice 1
  are UNVERIFIED/BLOCKED, not hidden.

## 6. Decided by the owner
- Approach A, Core + CLI first.
- Windows/PowerShell first, zero paid spend, host-native execution.
- No vendor name of the second host in pushed content.

## 7. Builder's calls (marked as mine, owner may override)
- Stack (pydantic + argparse + sqlite3), MIT license, repo at `~/projects/AgentOS`.
- Owner confirmation via TTY + typed phrase.
- Complexity score and recruit ranking are simple weighted heuristics, labeled uncalibrated until slice 3 benchmarks.
- Neutral adapter id `cc` for the second host. I write the owner's local `cc` host profile on this machine
  (git-excluded). The public repo explains the profile format without naming the host.
- The owner's pasted source spec is not stored in the repo, because it names the second host. Section numbers above (§17, §18, §49) refer to it.
- Canonical definitions are TOML (read with stdlib `tomllib`) instead of YAML, so there is no extra dependency.
- `eval record` needs an evaluator id different from the evaluated instance and its parent, plus at least
  one evidence reference (test command, file or log). Self-grading is rejected.
- Slice 1 can't stop a host from spawning a subagent without asking `agent admit` first. It only records and
  refuses on request. Blocking by hook is slice 2, and this is listed in LIMITATIONS.
- The Codex generator also writes a local marketplace file so `codex plugin marketplace add <dir>` works.
- GitHub repo `AgentOS` under the owner's account. Visibility (public/private) is confirmed with the owner before creating it.

## 8. Left to the builder
Exact table columns, internal function boundaries, message wording, exit-code mapping details,
test fixture design.
