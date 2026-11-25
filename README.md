# AgentOS

A local ledger and referee for multi-agent coding sessions.

Your coding host (Codex, or another host you describe with a profile) does the thinking: it
plans, writes code and starts workers. AgentOS keeps the books and says yes or no:

- **Admission.** The host asks before starting a worker. AgentOS checks concurrency, depth,
  per-task and budget limits, the emergency stop, and whether the template is in good standing.
  A denial lists every reason.
- **Lifecycle.** Each worker moves through 17 explicit states. Illegal moves are refused and audited.
- **Evaluations.** Workers are graded by someone else (never themselves, their parent or their
  children), and only with evidence. Retirement needs at least 5 evaluations and 2 independent
  failing evaluators, plus the owner.
- **Memory.** Per-project knowledge with provenance, versions and keyword search. Only validated
  knowledge is shared across projects.
- **Handovers.** A sanitized summary another session or host can resume once, with warnings if
  the repository moved on.
- **Audit log.** Every change is written to a hash-chained log that `agentos audit verify` checks.
- **Owner controls.** Raising limits, paid budgets, retiring templates, restore and lifting the
  emergency stop need the human owner typing a confirmation at a real console.

AgentOS never calls a model, never uses the network, and spends nothing.

## Install (Windows)

Needs Python 3.11 or newer and Git.

```powershell
git clone REPO_URL AgentOS
cd AgentOS
powershell -ExecutionPolicy Bypass -File scripts\install.ps1            # dry run: shows what it would do
powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -Apply     # install
```

The installer creates `%USERPROFILE%\.agentos\venv`, installs this checkout into it, adds
`%USERPROFILE%\.agentos\bin` to your user PATH, then runs `agentos init` and `agentos doctor`.
It never edits your Codex config. Add the plugin yourself:

```powershell
codex plugin marketplace add <path to AgentOS>\plugins\codex
codex plugin add agentos@agentos
```

Uninstall with `scripts\uninstall.ps1 -Apply`. State, backups and handovers are kept unless you add `-PurgeState`.

## Quickstart

```powershell
agentos project activate .                       # once per repository
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

`--json` gives machine-readable output. Exit codes: 0 ok, 2 usage or not initialized,
3 policy denied, 4 not found, 5 integrity failure.

## Plugins for hosts

`plugins/codex/` is generated from `definitions/` with `agentos gen codex`. Other hosts:
`agentos gen host --profile <profile.toml> --out <dir>`. See [docs/HOST_PROFILE.md](docs/HOST_PROFILE.md).

## Status

Version 0.1.0 is slice 1: the core ledger and CLI. Read [docs/LIMITATIONS.md](docs/LIMITATIONS.md),
in particular: **a host that never asks can still start workers**, because blocking hooks come in
slice 2. [reports/AUDIT.md](reports/AUDIT.md) lists every audit criterion with its evidence or
the reason it is not done yet.

## Development

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e . -r requirements-lock.txt
.venv\Scripts\python -m pytest -q                 # live host tests are excluded by default
.venv\Scripts\ruff check src tests
```

MIT licensed.
