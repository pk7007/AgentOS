# AgentOS

**A local ledger and referee for multi-agent coding sessions.**

AI coding hosts such as Codex can split work across many sub-agents. That works until it
doesn't: too many workers at once, agents grading their own work, lost context between
sessions, secrets in notes, no record of who did what. AgentOS is a small command-line tool
the host consults before and after each step. It keeps the books, enforces limits, and
refuses what isn't allowed.

- **The host is the brain.** It plans, writes code and decides. AgentOS never calls a model.
- **AgentOS is the ledger.** Tasks, agents, evaluations, memory and handovers live in one SQLite file.
- **AgentOS is the referee.** Every request to start a worker gets a yes, or a no with every reason.
- **You are the owner.** Risky changes need you at a real terminal, typing a confirmation.

It runs entirely on your machine: no server, no network calls, no cost.

> **Status: version 0.1.0 (slice 1, the core ledger and CLI).** It works and is tested
> (303 tests, 94% branch coverage), but a host that never asks AgentOS can still start
> workers. Blocking that comes in slice 2. See [Limitations](docs/LIMITATIONS.md) and the
> [audit report](reports/AUDIT.md).

## Contents

- [How it works](#how-it-works)
- [Install](#install)
- [Connect Codex](#connect-codex)
- [Quickstart](#quickstart)
- [Core concepts](#core-concepts)
- [Command reference](#command-reference)
- [Limits and budgets](#limits-and-budgets)
- [Owner-only actions](#owner-only-actions)
- [Where your data lives](#where-your-data-lives)
- [Other hosts](#other-hosts)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Project layout](#project-layout)

## How it works

```mermaid
sequenceDiagram
    participant H as Host session (Codex)
    participant A as agentos CLI
    participant D as SQLite ledger + audit log
    participant O as Owner (you)
    H->>A: agent admit --task T --template implementer
    A->>D: check limits, budget, stop flag, template standing
    alt allowed
        A-->>H: exit 0 + instance id
        H->>H: start the worker
        H->>A: agent transition <id> RUNNING ... COMPLETED
        H->>A: eval record <id> --evaluator reviewer --evidence ...
    else denied
        A-->>H: exit 3 + every reason (max_concurrent, budget_exceeded, ...)
        H->>H: do not start it; wait, do it itself, or report
    end
    O->>A: limits set / template retire / stop --lift
    A->>O: "Type exactly: I APPROVE ..." (real console only)
```

Every change, allowed or denied, is appended to a hash-chained audit log. `agentos audit verify`
recomputes the chain and fails (exit 5) if any row was edited or deleted.

## Install

**Requirements:** Windows 10 or 11, Python 3.11 or newer on PATH, Git.

```powershell
git clone https://github.com/pk7007/AgentOS.git
cd AgentOS
powershell -ExecutionPolicy Bypass -File scripts\install.ps1            # dry run: prints what it would do
powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -Apply     # install
```

With `-Apply`, the installer:

1. checks your Python version,
2. creates a private virtual environment in `%USERPROFILE%\.agentos\venv`,
3. installs this checkout into it (editable, so keep the cloned folder where it is),
4. writes `%USERPROFILE%\.agentos\bin\agentos.cmd`,
5. adds that `bin` folder to your **user** PATH and prints the old and new PATH (skip with `-NoPath`),
6. runs `agentos init`, `agentos template seed` and `agentos doctor`.

Open a new terminal afterwards so the PATH change applies, then check:

```powershell
agentos --version
agentos doctor
```

Installer options: `-AgentosHome <folder>` (default `%USERPROFILE%\.agentos`),
`-Python <path to python.exe>`, `-NoPath`.

**Uninstall:** `scripts\uninstall.ps1 -Apply` removes the virtual environment, the launcher and
the PATH entry. Your database, backups and handovers are kept. Add `-PurgeState` to delete them
too; a final backup is still written to `%USERPROFILE%\.agentos\agentos-final-<time>.db` first.

## Connect Codex

The installer never edits your Codex configuration. Add the plugin yourself:

```powershell
codex plugin marketplace add <path to AgentOS>\plugins\codex
codex plugin add agentos@agentos
codex plugin list            # should show: agentos@agentos  installed, enabled
```

The plugin gives Codex:

- the **`agentos` skill**, which tells the session how to size work, ask before starting
  workers, grade with evidence, save knowledge and hand over;
- **six agent definitions** (`lead`, `planner`, `implementer`, `reviewer`, `researcher`,
  `recovery`) in `plugins/codex/agents/`;
- an optional **`config-snippet.toml`** that registers those agents and sets
  `max_threads = 4` and `max_depth = 2` to match AgentOS's defaults. Copy what you want
  into your own Codex config by hand.

## Quickstart

Run these inside a Git repository you are working on:

```powershell
agentos project activate .                       # turn AgentOS on for this repo
agentos plan score --tasks 4 --depth 2 --workstreams 2 --files 10 --difficulty 3 --uncertainty 2 --risk 2 --verify 3
agentos task add "Add login rate limit" --cap testing --accept "tests pass" --json
agentos recruit --cap review --json              # best template for a capability
agentos agent admit --task <task id> --template implementer --host codex --json   # exit 3 = do not start it
agentos agent transition <instance id> RUNNING
agentos eval record <instance id> --evaluator reviewer-1 --category coding --score quality=90 --evidence "pytest -q: 41 passed"
agentos memory add project "Rate limit lives in middleware, not handlers" --source docs/adr-7.md
agentos handover create --objective "rate limiting" --next "wire the config flag" --host codex
agentos audit verify
```

In normal use you don't type most of these: the Codex session runs them, guided by the skill.
You mostly use `status`, `audit verify`, `stop`, and the owner-only commands.

## Core concepts

### Projects

AgentOS is off for a repository until you run `project activate`. A project is identified by its
Git root, so subfolders and different spellings of the same path map to one project. Tasks,
agents, memory and handovers belong to exactly one project.

### Tasks

Tasks form a dependency graph per project. Cycles and cross-project dependencies are refused,
a task can't start until its dependencies are done, and retries are capped (`max_retries`).
States: `pending`, `running`, `blocked`, `done`, `failed`, `cancelled`.
`task ready` lists what can start now, highest priority first.

### Templates and agents

A **template** is a stored, versioned agent configuration: role, capabilities, instructions,
whether it is read-only, and whether it may delegate. An **agent instance** is one run of a
template on one task. Instances move through 17 states:

`PROPOSED`, `RECRUITED`, `VALIDATING`, `AVAILABLE`, `ASSIGNED`, `RUNNING`, `WAITING`, `BLOCKED`,
`REVIEWING`, `COMPLETED`, `FAILED`, `RETRAINING`, `QUARANTINED`, `SUSPENDED`, `CANCELLED`,
`TERMINATED`, `ARCHIVED`.

Only legal moves are allowed (for example RUNNING to COMPLETED, but not RUNNING to ARCHIVED),
and refused moves are audited. `ASSIGNED`, `RUNNING`, `WAITING`, `BLOCKED` and `REVIEWING`
count as active and hold a concurrency slot. AgentOS can't kill a host's worker, so TERMINATED
shows as `TERMINATED (unconfirmed)` unless the host passes `--confirmed`.

### Admission

`agent admit` is the gate. It collects **every** reason to refuse, not just the first:

| Reason | Meaning |
| --- | --- |
| `emergency_stop` | the owner or anyone engaged `agentos stop` |
| `project_inactive` | the repo isn't activated |
| `task_not_found`, `task_not_open` | the task doesn't exist or is finished |
| `template_unavailable` | the template is suspended, quarantined, retired or unknown |
| `parent_not_active`, `parent_cannot_delegate` | the delegating agent isn't running or may not delegate |
| `max_depth`, `max_concurrent`, `max_agents_per_task` | a limit would be exceeded |
| `duplicate` | the same template is already active on this task |
| `budget_exceeded:<scope>:<kind>` | a budget would be exceeded |

Admission is atomic: twelve processes racing for four slots get exactly four.

### Evaluations and performance

An evaluation scores one agent instance from 0 to 100 on any of: `quality` (25%), `accuracy`
(20%), `reliability` (15%), `instruction_compliance` (10%), `security_compliance` (10%),
`cost_efficiency` (8%), `speed` (7%), `collaboration` (5%). Missing keys are left out and the
weights renormalized.

- An agent can't be graded by itself, its parent or any ancestor, or its children or any descendant.
- Every evaluation needs evidence: a test command and result, a file or a log.
- `--flag security_violation` or `integrity_violation` quarantines the template immediately.
- `--external` marks a failure caused outside the agent's control; it doesn't count.

`perf show <template>` summarizes the results into a band (`elite` 95+, `reliable` 85+, `monitor`
70+, `improve` 50+, otherwise `suspend_review`) and a recommendation. With fewer than 5
evaluations it says `insufficient_evidence`. `retire_review` additionally needs at least two
different evaluators who gave failing grades, and actual retirement needs the owner.
Any sub-score under 30 is counted as critical even when the average looks fine.

`recruit --cap <capability>` ranks active templates by capability match, track record,
reliability and confidence. If nothing fits, it reports the gap rather than inventing a template.

### Memory

Knowledge is stored per project with its source, author, confidence and version, and searched
with full-text search. Layers: `working`, `episodic`, `semantic`, `procedural`, `performance`,
`failure`, `project`, `organizational`, `governance`.

- Records are only visible inside their own project.
- A record can be shared with all projects (`--org`) only if it is validated and in the
  `semantic`, `procedural`, `failure` or `organizational` layer.
- `memory correct` creates a new version; `memory delete` wipes the content and keeps a tombstone.
- Common secret formats (private keys, API keys, GitHub, AWS and Slack tokens, `password=` values)
  are redacted before anything is stored.

### Handovers

`handover create` writes a sanitized JSON summary of the project: tasks, active agents, pending
approvals, recent decisions, limits, budgets and the Git state. It never stores transcripts. A
later session, or another host, runs `handover resume <id>`. Each handover can be claimed only once,
and resume warns about `head_advanced`, `head_diverged`, `dirty_tree` and `orphaned_instances`.

### Approvals

For actions you want gated case by case, a host can `approval request <action> --params '<json>'`.
You `approval grant` it at your terminal. The approval is bound to that exact action and those
exact parameters, expires (default 60 minutes) and can be used once (`approval consume`).
`approval check` exits 0 only while a valid approval exists.

### Emergency stop

`agentos stop` is a big red button anyone can press: no new workers are admitted, and running
ones can still finish or be cancelled. Lifting it (`stop --lift`) needs the owner.

## Command reference

Add `--json` to any command for machine-readable output. Exit codes: `0` ok, `2` usage error or
not initialized, `3` refused by policy, `4` not found, `5` integrity failure.

| Group | Commands |
| --- | --- |
| System | `init`, `doctor`, `status`, `backup [--dest DIR]`, `restore FILE` (owner) |
| Audit | `audit verify`, `audit log [--limit N] [--kind KIND]` |
| Projects | `project activate [PATH]`, `project deactivate [PATH or ID]`, `project list` |
| Tasks | `task add TITLE`, `task dep TASK --on OTHER`, `task list`, `task ready`, `task inspect`, `task start / done / fail / block / cancel / retry / unblock TASK` |
| Planning | `plan score --tasks --depth --workstreams --files --difficulty --uncertainty --risk --verify` |
| Templates | `template add FILE`, `template seed`, `template list`, `template inspect ID`, `template suspend / quarantine / retire / reinstate ID --reason` |
| Agents | `agent admit --task --template [--parent] [--host]`, `agent transition ID STATE`, `agent list [--active]`, `agent inspect ID` |
| Evaluations | `eval record ID --evaluator --category --score <key>=N --evidence`, `perf show TEMPLATE`, `recruit --cap CAP [--high-risk]` |
| Memory | `memory add LAYER TEXT`, `memory search QUERY`, `memory inspect ID`, `memory correct ID TEXT`, `memory delete ID`, `memory export [--out FILE]` |
| Handovers | `handover create --objective --next`, `handover resume ID`, `handover list` |
| Governance | `limits show / set / host`, `budget set / show`, `stop [--lift]`, `approval request / grant / deny / consume / check / list` |
| Plugins | `gen codex [--out] [--force]`, `gen host --profile FILE --out DIR` |

Every command has `--help`. Commands that act on a project take `--project PATH or ID` and
default to the current directory.

## Limits and budgets

| Limit | Default | Meaning |
| --- | --- | --- |
| `max_concurrent` | 4 | active agents at once, across all projects |
| `max_depth` | 2 | how deep delegation can go |
| `max_retries` | 2 | retries per task |
| `max_agents_per_task` | 12 | agent runs per task |
| `max_paid_spend_usd` | 0.0 | cap on any `usd` budget |
| `max_remediation_rounds` | 5 | fix-and-review rounds |

Anyone may **lower** a limit; **raising** one needs the owner. A host can record its own
stricter limit with `limits host`, and the strictest value wins.

Budgets can be set per `global`, `project` or `task` scope, for `agent_runs`, `tokens_est` or
`usd`, for example:

```powershell
agentos budget set project tokens_est 2000000 --id <project id>
agentos budget show
```

Token figures are estimates the host reports; AgentOS can't see real usage.

## Owner-only actions

These ask you to type `I APPROVE <action>` at an interactive console. Agents run without one, so
they can't confirm, and there is no environment variable or flag that skips the prompt.

- raising any limit
- setting a `usd` budget above `max_paid_spend_usd`
- retiring a template, or releasing one from quarantine
- granting an approval
- lifting the emergency stop
- restoring the database from a backup
- changing protected settings

## Where your data lives

| Path | Contents |
| --- | --- |
| `%USERPROFILE%\.agentos\state\agentos.db` | the ledger and audit log (SQLite, WAL mode) |
| `%USERPROFILE%\.agentos\backups\` | `agentos backup` output |
| `%USERPROFILE%\.agentos\handovers\` | handover JSON files |
| `%USERPROFILE%\.agentos\venv\`, `bin\` | the installed program |

Environment variables: `AGENTOS_HOME` moves all of the above; `AGENTOS_ACTOR` sets the name
recorded in the audit log (default `host`).

Back up with `agentos backup`. Restoring (`agentos restore FILE`) checks the file is a valid
AgentOS database with a schema this version understands, and keeps a safety copy of the
database it replaces.

## Other hosts

Any host that loads plugins from a folder of files can be described with a five-line TOML
profile, and `agentos gen host --profile <file> --out <dir>` writes its manifest, agents,
skill and a short instructions file. See [docs/HOST_PROFILE.md](docs/HOST_PROFILE.md).
Generated files you edit by hand are never overwritten without `--force`.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `agentos` is not recognized | open a new terminal after installing; check `%USERPROFILE%\.agentos\bin` is on your user PATH |
| `not initialized; run: agentos init` (exit 2) | run `agentos init` |
| `project is not activated` (exit 3) | run `agentos project activate .` in the repo |
| `recruit` finds nothing | run `agentos template seed` to load the bundled templates |
| `owner confirmation needs an interactive terminal` | run the command yourself in a normal terminal, not through an agent |
| `audit verify` fails (exit 5) | the database was changed outside AgentOS; restore from a backup and investigate |
| `doctor` shows `codex_cli: UNSUPPORTED` | the Codex CLI isn't on PATH; AgentOS still works, the plugin just can't be used |

## Development

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e . -r requirements-lock.txt
.venv\Scripts\python -m pytest -q          # 303 tests; the live host test is excluded
.venv\Scripts\ruff check src tests
.venv\Scripts\python -m pytest -m live     # runs a real Codex session (uses your Codex quota)
```

After changing anything in `definitions/`, regenerate the committed plugin with
`agentos gen codex --force`. A test fails if `plugins/codex/` is out of date, and another parses
every `agentos` command shown in the skill and in this README.

## Project layout

```
definitions/          source of truth for agents, the skill and plugin metadata
plugins/codex/        generated Codex plugin (committed)
src/agentos/          the package: one module per concern
  cli/                one module per command group
  gen/                plugin generators
  migrations/         SQLite schema
scripts/              install.ps1, uninstall.ps1
tests/                unit, integration, security, concurrency and live tests
docs/                 limitations, host profiles, design spec and plan
reports/AUDIT.md      criterion-by-criterion audit with evidence
```

## License

MIT. See [LICENSE](LICENSE).
