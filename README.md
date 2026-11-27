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

> **Status: version 0.2.0.** The ledger, the runtime spawn gate, the workforce, self-improvement,
> organisational intelligence, visibility and worker coordination all work and are tested (see the
> [audit report](reports/AUDIT.md) for the current test count and coverage). Where the host runs AgentOS's
> hooks, a worker that was not admitted is refused at spawn; a host without hooks can still start workers.
> Live Codex sessions have not been run (no quota). See [Limitations](docs/LIMITATIONS.md) and the
> [Phase 9 scores](reports/PHASE9_SCORES.md) and [host compatibility](reports/COMPATIBILITY.md).

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
- [Host adapters](#host-adapters)
- [Troubleshooting](#troubleshooting) (more in [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md))
- [Recovery runbook](docs/RUNBOOK.md), [worked examples](docs/EXAMPLES.md), [full command reference](docs/CLI.md), [every refusal reason](docs/REASONS.md)
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
        H->>A: evidence run -- pytest -q (AgentOS runs it and records the result)
        H->>A: eval record <id> --evaluator <reviewer instance> --evidence evd_...
    else denied
        A-->>H: exit 3 + every reason (max_concurrent, budget_exceeded, ...)
        H->>H: do not start it; wait, do it itself, or report
    end
    O->>A: limits set / template retire / stop --lift
    A->>O: "Type exactly: I APPROVE ..." (real console only)
```

Every change, allowed or denied, is appended to a hash-chained audit log. `agentos audit verify`
recomputes the chain and fails (exit 5) if any row was edited, deleted or cut off the end. To catch
a rewrite of the *whole* chain, save `agentos audit anchor --out <file>` somewhere agents can't
write and later run `agentos audit verify --anchor <file>`.

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
  into your own Codex config by hand;
- **runtime hooks** (`hooks/hooks.json`) that make Codex itself ask AgentOS before it spawns a
  subagent. They do nothing until you trust them (next section).

### Turn on enforced admission (hooks)

Without hooks, admission is cooperative: the skill tells Codex to ask `agent admit`
first, but nothing stops a session that doesn't. With the hooks trusted, Codex runs
`agentos hook run codex` at three points:

| Codex event | What AgentOS does |
| --- | --- |
| before `spawn_agent` | refuses the spawn unless an admitted worker is waiting in this project (an `agent admit` instance in ASSIGNED that no subagent has claimed). Put the instance id in the spawn message to choose one; otherwise the oldest is used. Every spawn is refused during an emergency stop. |
| subagent starts | binds Codex's agent id to that instance and moves it to RUNNING. A subagent with no ticket is recorded (`runtime.unadmitted_subagent`) and told to stop; Codex doesn't let this hook block it. |
| subagent stops | records the stop. A cancel or termination you asked for earlier is confirmed automatically, which frees its slot. |

To turn it on, after installing or updating the plugin:

1. Check `agentos --version` works in a **new** terminal; Codex starts the hook by that name.
2. In Codex, open `/hooks` (desktop app: **Settings > Hooks**), review the three AgentOS hooks
   and trust them. Codex skips a hook again whenever its content changes, until you re-trust it.

`agentos hook bindings` shows which subagent runs which instance. If the hook itself fails, the
spawn is refused and other tools are unaffected. Folders that aren't an activated project are
left alone. `agentos hook config codex` prints the hooks file if you'd rather put it in
`%USERPROFILE%\.codex\hooks.json` yourself.

Optional and slower: `agentos hook config codex --guard-tools` checks **every** tool call, so a
cancelled worker's calls are refused. Use that file *instead of* the plugin hooks; if both run,
a spawn is still claimed only once, but each call starts `agentos` twice. Whether Codex puts the
subagent's `agent_id` on its tool-call events is not verified yet (the second host, `cc`, does);
without it this guard can't tell a worker's calls apart and lets them through.

## Quickstart

Run these inside a Git repository you are working on:

```powershell
agentos project activate .                       # turn AgentOS on for this repo
agentos plan score --tasks 4 --depth 2 --workstreams 2 --files 10 --difficulty 3 --uncertainty 2 --risk 2 --verify 3
agentos task add "Add login rate limit" --cap testing --accept "tests pass" --json
agentos recruit --cap review --json              # best template for a capability
agentos agent admit --task <task id> --template implementer --host codex --json   # exit 3 = do not start it
agentos agent transition <instance id> RUNNING
agentos evidence run -- pytest -q                # AgentOS runs it and records the real result: evd_...
agentos eval record <instance id> --evaluator <reviewer instance id> --category coding --score quality=90 --score accuracy=85 --score reliability=85 --score instruction_compliance=90 --score security_compliance=90 --score cost_efficiency=80 --score speed=80 --score collaboration=85 --evidence <evd id>
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
count as active. AgentOS can't kill a host's worker, so a worker keeps its concurrency slot after
`CANCELLED`, and after a `TERMINATED` the host didn't confirm (shown as `TERMINATED (unconfirmed)`),
until the host confirms the runtime stopped: `agent confirm-stop <id>` or
`agent transition <id> TERMINATED --confirmed`. Moving an agent back into active work (for example
FAILED to ASSIGNED) goes through the same checks as a new admission and uses another agent run.

### Admission

`agent admit` is the gate. It collects **every** reason to refuse, not just the first:

| Reason | Meaning |
| --- | --- |
| `emergency_stop` | the owner or anyone engaged `agentos stop` |
| `project_inactive` | the repo isn't activated |
| `task_not_found`, `task_not_open` | the task doesn't exist or is finished |
| `dependencies_incomplete` | a task this one depends on isn't done |
| `template_unavailable` | the template is suspended, quarantined, retired or unknown |
| `capability_mismatch` | the template lacks a capability the task requires (`--cap`) |
| `high_risk_unproven` | `high` risk task: the template needs 3+ evaluations averaging 85+, or an owner approval |
| `owner_approval_required` | `critical` risk task: always needs an owner approval |
| `parent_not_active`, `parent_cannot_delegate` | the delegating agent isn't running or may not delegate |
| `parent_cross_project` | the delegating agent belongs to another project |
| `max_depth`, `max_concurrent`, `max_agents_per_task` | a limit would be exceeded |
| `duplicate` | the same template is already active on this task |
| `budget_exceeded:<scope>:<kind>` | a budget would be exceeded |
| `budget_exhausted:<scope>:<kind>` | a token or paid-spend budget is already used up |

For a high-risk or critical task, ask the owner:
`agentos approval request admit_high_risk --params '{"task_id": "<task>", "template_id": "<template>"}'`.
Once granted, the next matching admission uses it up.

Admission is atomic: twelve processes racing for four slots get exactly four.

### Evaluations and performance

An evaluation scores one agent instance from 0 to 100 on **all** of: `quality` (25%), `accuracy`
(20%), `reliability` (15%), `instruction_compliance` (10%), `security_compliance` (10%),
`cost_efficiency` (8%), `speed` (7%), `collaboration` (5%). Leaving a score out is refused, so a
grade can't be built from only the flattering parts.

- The evaluator is another registered agent instance of the same project (or `owner`, which asks
  for owner confirmation). It can't be the agent itself, its parent or any ancestor, or its
  children or any descendant. Each evaluator grades an agent once per category.
- Every evaluation needs at least one `evd_` evidence id from `agentos evidence run -- <command>`.
  AgentOS runs that command itself in the repository and records the exact command, exit code,
  output hashes, a redacted output tail and the Git HEAD, so the result can't be invented. Extra
  free-text notes are allowed alongside it.
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
- Common secret formats are redacted before anything is stored: private keys, OpenAI-style,
  GitHub, GitLab, npm, AWS, Slack, Stripe and Google keys, JWTs, `Bearer` tokens, passwords in URLs,
  and values of keys such as `password`, `client_secret` or `AWS_SECRET_ACCESS_KEY`, including in
  JSON. Redaction is pattern-based, so it can miss secrets in formats it doesn't know.

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

### Objectives (the Boss loop)

For work bigger than one task, the host runs an objective: `boss start` records it with testable
acceptance criteria, `boss plan` applies the host's decomposition (JSON) in one transaction,
`boss next` says what to start by critical path and free slots, `boss bottlenecks` and
`boss review` (nine executive checks: operations, engineering, hr, finance, intelligence,
security, data, risk, quality) show what is stuck, `boss recover` handles a failed task,
`boss accept` takes a done task only on an independent passing grade, and `boss deliver` closes
the objective only with a passing evidence record for every criterion. The executive functions
are checks, not workers; a department lead is suggested only for large objectives. Details:
[docs/BOSS.md](docs/BOSS.md).

### Agent Factory and workforce

When no template covers a task, `factory recruit` drafts a specialist from the closest existing
template, validates it (safety rules always appended; rule-loosening text, secrets and oversized
configs refused), registers it and admits it. A specialist that asks for more than its base
template (write access, new tools, delegation, elevated security) waits for the owner's approval.
Specialists are temporary by default and expire after 72 hours unless busy; at most
`max_factory_templates` are live at once.

`workforce` keeps the team matched to the work and its record: `review` suspends templates that
keep failing, `rehab` and `probation` bring a weak one back with a better version, `succession`
names who could take over each template's work, `split` spreads a heavy task across parallel
parts, `contract` archives finished workers and dissolves empty departments, `terminate` stops a
worker safely and saves what it learned, and `transfer` hands unfinished work to a replacement
with a briefing. Retiring a template stays with the owner. Details:
[docs/WORKFORCE.md](docs/WORKFORCE.md).

### Self-improvement

After each accepted task and delivered objective, a retrospective collects the outcomes, grades
and evidence, separates what worked from what didn't, diagnoses recurring weaknesses and proposes
hypotheses (an instruction change for a template, or a recruitment weight). A change replaces
nothing until it wins a **champion-versus-challenger experiment**: the challenger runs as an
isolated candidate on fixed representative and held-out benchmark cases, every trial is checked by
AgentOS running the case's own command and graded by an evaluator of neither side, a regression
and security gate must pass, and only a clear, unflagged win with no loss on held-out cases is
promoted. Promoted changes are monitored and rolled back if they regress; what was learned is
kept as validated memory. Only instructions, descriptions, model and reasoning hints and bounded
recruitment weights can change this way; permissions, security, approvals, limits and ownership
cannot. Details: [docs/IMPROVE.md](docs/IMPROVE.md).

### Organisational intelligence

The `intel` commands turn the ledger into advice: how many workers of which kind the open work needs
(`staffing`), the cheapest model tier a task's risk and the worker's record justify (`route`), the
most useful memory within a token budget (`context`), checks proven often enough to become a
reusable skill (`skills`, `skill-create`), idle, overlapping or overloaded parts of the
organisation (`org`), recurring failures (`failures`), the winner among competing solutions to
one task (`compete`), an independent re-check of the core invariants (`governance`), what the
remaining work will cost (`forecast`), this project's history (`profile`) and lessons several
projects validated, ready to share (`lessons`, `share`). Simple, written-down rules; no model
calls, no spending. Details: [docs/INTEL.md](docs/INTEL.md).

### Seeing what is happening

`agentos dashboard` prints one screen: the emergency stop, owner pin and pending approvals, the
audit chain, slots in use, active workers, incidents, accepted and rejected changes, experiments
and progress per objective. Each `observe` view shows one part in full (for example `agentos observe incidents`):

| View | Shows |
| --- | --- |
| `agents [--all-projects]` | workers holding a slot now, with what the host's hooks reported (native agent id, start, stop) |
| `tree [--all]` | the worker hierarchy, parents and children |
| `progress` | tasks per objective by state, percent done, accepted tasks, blocked tasks |
| `recruitment` / `terminations` | admissions, refusals, new templates and transfers; terminations and stops the host has not confirmed |
| `performance` | each template's record: evaluations, mean, recent mean, band, recommendation |
| `resources` | slots, agent runs, estimated tokens and paid spend against every budget |
| `experiments` / `changes` | improvement experiments; accepted and rejected changes (experiments, new templates, rehabilitations, approvals) |
| `incidents` | security incidents, most severe first: unadmitted subagents, flagged evaluations, quarantines, refused spawns and tools, a broken audit chain |
| `controls` | the emergency stop, owner pin, limits and the exact commands to stop, cancel, terminate or quarantine |

Every figure comes from a ledger row or an audit event. The views only read.

### Coordination between workers

Workers that share a repository coordinate through the ledger:

- **Messages**: `agentos msg send --from <worker> --to <worker> <text>` (or `--to owner`, `--to all`);
  `agentos msg inbox <worker> --mark-read`. Bodies are redacted before they are stored. The host
  delivers them; AgentOS records them.
- **Escalations**: `agentos msg escalate --from <worker> <text>` puts a decision in front of the owner.
  The dashboard and `observe incidents` show it until the owner reads it.
- **Claims**: `agentos claim take <worker> <path>` before editing. A claim is exclusive: another active
  worker asking for the same path, a file inside a claimed folder, or a folder containing a claimed file
  is refused (`path_claimed`) and told who holds it. A claim of a worker that is no longer active is freed
  automatically, so a crashed worker never blocks the others.
- **Workflows**: `agentos workflow from-objective <objective> <name>` saves a delivered objective's task
  graph; `agentos workflow apply <objective> <name>` reuses it. Versions are kept and hashed; a changed
  stored workflow is refused (`tampered`).

### Worker health

A host reports `agentos health heartbeat <worker>` while a worker runs. `agentos health stale` lists active
workers not heard from for 15 minutes (configurable), and `agentos health reap` marks them failed, frees
their slots and retries their tasks with a different template, or escalates at the retry limit.

A circuit breaker suspends a template automatically after three evaluations in a row below 30, so a
template whose work fails badly stops being admitted at once. The workforce review's milder rule (three
failing evaluations below 50) still applies when the review runs. `agentos health breaker` shows the
breaker; `agentos health breaker --window 2 --floor 40` makes it stricter, and making it milder needs the
owner. Every change is a policy change (`agentos policy history`).

When a task fails its last retry, AgentOS escalates to the owner on its own: the dashboard and
`agentos observe incidents` show it until the owner reads it with `agentos msg inbox owner --mark-read`.

### Policy versions, retention and benchmarks

- `agentos policy show` prints the policy in force (limits, host and project limits, budgets, tunable
  values, the emergency stop) with a version number and a hash; `agentos policy history` lists every
  change with who made it. `agentos policy project-limit max_concurrent 2` tightens one project only.
- `agentos retention plan` counts read messages, old benchmark runs, released claims and deleted memory older
  than 90 days;
  `agentos retention apply` removes them (owner). The audit log is never pruned.
- `agentos bench run` measures admission, audit appends, memory search and chain verification on a
  scratch database, also after the ledger has grown; `agentos bench history` flags a run more than 1.5
  times slower than earlier ones.

### Integrations

- `agentos mcp serve` is a Model Context Protocol server over stdio with read-only tools: status, the
  dashboard, every `observe` view, memory search, routing advice, the policy and the governance check.
  Admission, grading and limits stay CLI commands, so the hooks and owner confirmations still gate them.
- `schemas/` holds JSON Schema files for templates, instances, admission requests and decisions, tasks,
  evaluations, evidence, memory records, limits and plans, generated from the models the code enforces
  (`agentos gen schemas`). A test fails if they drift.

### Emergency stop

`agentos stop` is a big red button anyone can press: no new workers are admitted, and running
ones can still finish or be cancelled. With the runtime hooks on, Codex also refuses every new
spawn. Lifting it (`stop --lift`) needs the owner.

## Command reference

Add `--json` to any command for machine-readable output. Exit codes: `0` ok, `2` usage error or
not initialized, `3` refused by policy, `4` not found, `5` integrity failure.

| Group | Commands |
| --- | --- |
| System | `init`, `doctor`, `status`, `backup [--dest DIR]`, `restore FILE` (owner) |
| Audit | `audit verify [--anchor FILE]`, `audit anchor [--out FILE]`, `audit log [--limit N] [--kind KIND]` |
| Projects | `project activate [PATH]`, `project deactivate [PATH or ID]`, `project list` |
| Tasks | `task add TITLE`, `task dep TASK --on OTHER`, `task list`, `task ready`, `task inspect`, `task start / done / fail / block / cancel / retry / unblock TASK` |
| Planning | `plan score --tasks --depth --workstreams --files --difficulty --uncertainty --risk --verify` |
| Agent Factory | `factory recruit --task --host [--parent] [--permanent]`, `factory propose --cap CAP [--task] [--file SPEC.toml] [--permanent] [--ttl-hours]`, `factory register / show ID`, `factory reject ID --reason`, `factory expire`, `factory list [--status]` |
| Workforce | `workforce review`, `workforce rehab TEMPLATE --file V2.toml`, `workforce probation TEMPLATE`, `workforce succession`, `workforce split TASK [--parts N]`, `workforce contract`, `workforce terminate ID --reason [--note]`, `workforce transfer ID --host [--to TEMPLATE] [--note]`, `workforce transfers` |
| Objectives (Boss) | `boss start TITLE --accept CRITERION [--statement] [8 complexity flags]`, `boss plan OBJ --file PLAN.json`, `boss next / bottlenecks / review / show OBJ`, `boss accept TASK --eval EV_ID [--min-score]`, `boss recover TASK`, `boss deliver OBJ --criterion N=EVD_ID`, `boss list` |
| Self-improvement | `improve retro [--task / --objective / --show ID]`, `improve case --suite --title --split [--cap] -- COMMAND...`, `improve cases`, `improve propose --suite (--from-retro ID / --template ID --file F / --policy NAME --value N)`, `improve trial EXP CASE --arm --host`, `improve check TRIAL`, `improve score TRIAL EVAL`, `improve gate EXP -- COMMAND...`, `improve status / decide / show EXP`, `improve abandon EXP --reason`, `improve monitor`, `improve experiments`, `improve policies` |
| Templates | `template add FILE` (an existing id needs the owner), `template seed`, `template list`, `template inspect ID`, `template suspend / quarantine / retire / reinstate ID --reason` |
| Agents | `agent admit --task --template [--parent] [--host]`, `agent transition ID STATE [--confirmed]`, `agent confirm-stop ID`, `agent list [--active]`, `agent inspect ID` |
| Evidence | `evidence run [--timeout S] -- COMMAND...`, `evidence show ID` |
| Evaluations | `eval record ID --evaluator INSTANCE --category --score <key>=N (all 8) --evidence EVD_ID`, `perf show TEMPLATE`, `recruit --cap CAP [--high-risk]` |
| Memory | `memory add LAYER TEXT`, `memory search QUERY`, `memory inspect ID`, `memory correct ID TEXT`, `memory delete ID`, `memory export [--out FILE]` |
| Handovers | `handover create --objective --next`, `handover resume ID`, `handover list` |
| Governance | `limits show / set / host`, `budget set / show / use`, `stop [--lift]`, `approval request / grant / deny / consume / check / list`, `owner pin set / clear / status` |
| Runtime hooks | `hook run HOST` (run by the host runtime, JSON on stdin), `hook bindings [--all]`, `hook config HOST [--guard-tools]` |
| Plugins | `gen codex [--out] [--force]`, `gen host --profile FILE --out DIR` |
| Intelligence | `intel staffing [--objective]`, `intel route TASK [--host H]`, `intel options TASK`, `intel context TASK [--budget N] [--record]`, `intel skills`, `intel skill-create EVIDENCE`, `intel org`, `intel failures [--record]`, `intel compete TASK`, `intel governance`, `intel forecast [--objective]`, `intel profile`, `intel lessons`, `intel share MEMORY`, `intel managers`, `intel calibration`, `intel memory-quality`, `intel reuse` |
| Visibility | `dashboard`, `observe agents / tree / progress / recruitment / terminations / performance / resources / experiments / changes / incidents / controls / timeline / spans` |
| Coordination | `msg send --from --to TEXT [--kind] [--task]`, `msg inbox WHO [--all] [--mark-read]`, `msg escalate --from TEXT`, `claim take ID PATH...`, `claim release ID [PATH...]`, `claim list`, `workflow save NAME --file F`, `workflow from-objective OBJ NAME`, `workflow list / show NAME`, `workflow apply OBJ NAME` |
| Health | `health heartbeat ID`, `health stale [--after-minutes N]`, `health reap [--after-minutes N]`, `health breaker [--window N] [--floor X]` |
| Policy and data | `policy show`, `policy history`, `policy project-limit FIELD VALUE`, `retention plan / apply [--days N]` |
| Benchmarks | `bench run [--n N] [--no-record]`, `bench history [--name]` |
| Integrations | `mcp serve`, `gen schemas`, `gen docs` |
| Host adapters | `host list`, `host install HOST [--dest DIR] [--profile F]`, `host drift HOST`, `host rollback HOST`, `host uninstall HOST [--force]`, `host bootstrap HOST [--remove]`, `host check HOST`, `host history [HOST]` |

Every command has `--help`. Commands that act on a project take `--project PATH or ID` and
default to the current directory. Commands that act on one task, agent or evidence record by id
refuse (exit 3, `cross_project`) when it belongs to a different project than the current one.

## Limits and budgets

| Limit | Default | Meaning |
| --- | --- | --- |
| `max_concurrent` | 4 | active agents at once, across all projects |
| `max_depth` | 2 | how deep delegation can go |
| `max_retries` | 2 | retries per task |
| `max_agents_per_task` | 12 | agent runs per task |
| `max_paid_spend_usd` | 0.0 | cap on any `usd` budget |
| `max_remediation_rounds` | 5 | fix-and-review rounds |
| `max_factory_templates` | 5 | factory specialists registered and active at once |

Anyone may **lower** a limit; **raising** one needs the owner. A host can record its own
stricter limit with `limits host`, and the strictest value wins.

Budgets can be set per `global`, `project` or `task` scope, for `agent_runs`, `tokens_est` or
`usd`, for example:

```powershell
agentos budget set project tokens_est 2000000 --id <project id>
agentos budget show
```

Token and paid-spend budgets are charged with `agentos budget use <instance> --tokens N` (or
`--usd X`) **before** the work: exit 3 means it would go over, so don't do it. Once a token or
paid-spend budget is used up, new admissions in that scope are refused (`budget_exhausted`).
Token figures are estimates the host reports; AgentOS can't see real usage.

## Owner-only actions

These ask you to type `I APPROVE <action>` at an interactive console. Agents run without one, so
they can't confirm, and there is no environment variable or flag that skips the prompt.

The phrase is shown in the prompt, so anything that can drive a terminal could type it. For a
second factor, set an owner PIN once with `agentos owner pin set`: every confirmation then also
asks for the PIN, unechoed. It is stored only as a salted scrypt hash and never logged.

- raising any limit
- setting a `usd` budget above `max_paid_spend_usd`
- retiring a template, or releasing one from quarantine
- replacing a working template by hand (`template add` with an id that exists); otherwise changes
  go through an `improve` experiment
- granting an approval
- lifting the emergency stop
- restoring the database from a backup
- changing protected settings
- grading an agent as `owner`, and setting or clearing the owner PIN

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

## Host adapters

`agentos host install codex` (or `cc`, with a profile) writes the plugin into a folder AgentOS
owns and prints the one command that registers it with the host; it never edits the host's own
configuration. Every update backs up the previous files, hand edits included, and
`host rollback` restores them. `host drift` reports hand edits, definitions that changed since
the install and host CLI updates. `host bootstrap` adds a short, removable block to a project's
instructions file, and `host check` reports how AgentOS coexists with other plugins such as
ECC. Work moves between hosts through handovers and the shared ledger, never through
conversation history. Details and the compatibility reports: [docs/HOSTS.md](docs/HOSTS.md).

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `agentos` is not recognized | open a new terminal after installing; check `%USERPROFILE%\.agentos\bin` is on your user PATH |
| `not initialized; run: agentos init` (exit 2) | run `agentos init` |
| `project is not activated` (exit 3) | run `agentos project activate .` in the repo |
| `recruit` finds nothing | run `agentos template seed` to load the bundled templates |
| `owner confirmation needs an interactive terminal` | run the command yourself in a normal terminal, not through an agent |
| `audit verify` fails (exit 5) | the database was changed outside AgentOS (`reason` says how); restore from a backup and investigate |
| admission says `max_concurrent` but nothing is running | a CANCELLED or unconfirmed TERMINATED agent still holds a slot; once its worker is really gone, `agentos agent confirm-stop <id>` |
| `cross_project` (exit 3) | run the command from the record's repository, or pass `--project` |
| `unverified_evidence` (exit 3) | run the check through `agentos evidence run -- <command>` and pass the `evd_` id |
| Codex refuses a spawn: `no admitted worker is waiting` | admit the worker first (`agent admit` with `--host codex`); spawn only if it is admitted |
| Codex refuses a spawn: `not admitted and waiting` | the instance id in the spawn message was already used, belongs to another project or isn't ASSIGNED; check `agentos agent list` |
| the AgentOS hooks never run | trust them in Codex `/hooks`; check `agentos --version` works in a new terminal |
| `path_claimed` (exit 3) | another active worker holds the path; message it or wait (see docs/TROUBLESHOOTING.md) |
| a template was suspended without a review | the circuit breaker tripped (three evaluations below 30); see `agentos observe incidents` |
| `doctor` shows `codex_cli: UNSUPPORTED` | the Codex CLI isn't on PATH; AgentOS still works, the plugin just can't be used |

## Development

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install --require-hashes -r requirements-lock.txt
.venv\Scripts\python -m pip install -e . --no-deps
.venv\Scripts\python -m pytest -q          # the live host tests are excluded
.venv\Scripts\ruff check src tests
.venv\Scripts\python -m pytest -m live     # runs a real Codex session (uses your Codex quota)
```

After changing anything in `definitions/`, regenerate the committed plugin with
`agentos gen codex --force`; after changing a model or a command, run `agentos gen schemas` and
`agentos gen docs`. Tests fail if `plugins/codex/`, `schemas/` or `docs/CLI.md` is out of date, and another
parses every `agentos` command shown in the skill, this README and the guides in `docs/`. After changing a
pin in `requirements-lock.txt`, run `python scripts/lock_hashes.py` to refresh its hashes.

## Project layout

```
definitions/          source of truth for agents, the skill and plugin metadata
plugins/codex/        generated Codex plugin (committed)
src/agentos/          the package: one module per concern
  cli/                one module per command group
  gen/                plugin generators
  migrations/         SQLite schema
scripts/              install.ps1, uninstall.ps1, lock_hashes.py
schemas/              generated JSON Schema files
tests/                unit, integration, security, concurrency and live tests
docs/                 limitations, host profiles, design spec and plan
reports/AUDIT.md      criterion-by-criterion audit with evidence
```

## License

MIT. See [LICENSE](LICENSE).
