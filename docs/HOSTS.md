# Host adapters: install, update, roll back, check

AgentOS works with two hosts today: **Codex** and a second host called `cc` throughout this
repository. Both are generated from the same definitions (`definitions/agents`,
`definitions/skills`, `definitions/plugin.toml`), share one ledger in `~/.agentos`, and hand work
to each other through structured handovers.

| | Codex | `cc` |
| --- | --- | --- |
| File names | built in | from your profile (`~/.agentos/hosts/cc.toml`; see [HOST_PROFILE.md](HOST_PROFILE.md)) |
| Skill | `skills/agentos/SKILL.md` | `<skills_dir>/agentos/SKILL.md` |
| Agents | `agents/<id>.toml` (custom agent files) + `config-snippet.toml` | `<agents_dir>/<id>.md` (front matter: name, description, tools, model) |
| Hooks | `hooks/hooks.json`: PreToolUse (spawn tool), SubagentStart, SubagentStop | same events, from `hooks_file` |
| Spawn tools gated | `spawn_agent`, `Agent` | `Agent`, `Task` |
| Project bootstrap | `AGENTS.md` | the profile's `instructions_file` |

## Global installation

```powershell
.\scripts\install.ps1 -Apply          # the agentos command, once per machine
agentos init
agentos host install codex             # writes ~/.agentos/plugins/codex and prints the register command
agentos host install cc                # needs ~/.agentos/hosts/cc.toml
```

`host install` never edits a host's own configuration. It copies the generated plugin into a
folder AgentOS owns and prints the one command that registers it (for Codex:
`codex plugin marketplace add <folder>`, then enable it in `/plugins`). It refuses a folder that
is not empty and holds no AgentOS install.

## Per-project activation

```powershell
cd <repo>
agentos project activate
agentos host bootstrap codex           # or cc
```

`host bootstrap` adds a short block, between `<!-- agentos:begin -->` and `<!-- agentos:end -->`,
to the project's instructions file. Text outside the block is never touched; `--remove` takes the
block out again (and deletes the file if AgentOS created it).

## Keeping it current, and undoing an update

| Command | What it does |
| --- | --- |
| `agentos host list` | every host: configured or not, capabilities, the host CLI's `--version`, the current install |
| `agentos host drift <host>` | exit 3 when anything changed: files edited or deleted by hand, files the current definitions would generate differently (`stale`), or a host CLI that was updated since the install |
| `agentos host install <host>` | updates in place. The files the last install left, **including your hand edits**, are backed up to `~/.agentos/host-backups/<host>/<install>/` first |
| `agentos host rollback <host>` | restores exactly what the previous install left, hand edits included |
| `agentos host uninstall <host> [--force]` | removes the installed files; files you edited are kept unless `--force` |
| `agentos host history [<host>]` | every install, update, rollback and removal; each is also in the audit log |

## Coexistence with other plugins (ECC and others)

`agentos host check <host>` scans the folders your profile names (`plugins_dir`, `agents_home`)
and reports:

- other plugins' hooks on the same events (PreToolUse on a spawn tool, SubagentStart, SubagentStop).
  Both hosts run every matching hook, and a deny from any hook blocks the call, so another
  plugin's hook cannot turn an AgentOS refusal into an allow;
- agents with the same name as ours. Plugin agents are namespaced by plugin, so they don't
  replace each other;
- a **second AgentOS hook set** (verdict `conflict`, exit 3): two would each claim an admission
  ticket for one spawn. Keep one install.

## Moving work between hosts

Work started under one host continues under the other through a handover, never through
conversation history:

```powershell
agentos handover create --objective "..." --next "the very next step" --host codex --json
agentos handover resume <ho_id> --host cc --json
```

The handover holds the objective, the next action, task states, active workers, pending
approvals, recent decisions, the Git state, limits and budgets, all redacted. Memory, evaluations,
templates and the audit log are the same store for every host, so what one host learned is there
for the other.

## Compatibility reports

Checked on Windows 11 on 2026-11-27. No model session was run for these checks.

### Codex (codex-cli 0.171.0)

| Check | Result |
| --- | --- |
| Plugin accepted | `codex plugin marketplace add <install folder>` in a throwaway `CODEX_HOME`: "Added marketplace `agentos`"; listed by `codex plugin marketplace list` |
| Plugin enabled, skill and agents in cache | verified earlier on the same version (`reports/AUDIT.md`, N) |
| Hooks discovered | all three events, untrusted until the owner trusts them (`integration/test_codex_hook_discovery.py`) |
| Manifest | `.codex-plugin/plugin.json`. Current docs prefer a root `plugin.json` and keep this path as a supported fallback |
| Config snippet | `[agents] max_threads`, `max_depth`. Current docs list `max_threads` as a legacy alias of `max_concurrent_threads_per_session` and do not list `max_depth`; the snippet is only copied by hand |
| Plugin hooks | current docs: plugin lifecycle hooks run only for manually installed plugins, after the user trusts them |
| Live spawn through the hook | **BLOCKED**: no Codex quota left on this account |

### `cc` (version 2.1.181)

| Check | Result |
| --- | --- |
| Plugin validates | the host's own `plugin validate` on the installed folder: passed, no warnings |
| Hooks | PreToolUse on `Agent`/`Task`, SubagentStart, SubagentStop; a live spawn gate ran in Phase 2 |
| Coexistence with ECC (installed) | `host check cc`: compatible. ECC has two PreToolUse hooks matching every tool; they run alongside the AgentOS hook. Same-named agents: `planner`, `reviewer` (namespaced, no clash). No second AgentOS hook set |
| Drift, update with backup, rollback | run against the real install folder: drift found the profile change, the update backed up the old files, rollback restored them, a fresh install reported `in_sync`, and `audit verify` passed |

### Both directions

| Direction | Ledger path (CLI) | Live host sessions |
| --- | --- | --- |
| Codex → `cc` | VERIFIED: `integration/test_cli_host.py::test_work_and_learning_cross_hosts_both_ways[codex-cc]` | **BLOCKED** (needs a live Codex session; no quota) |
| `cc` → Codex | VERIFIED: `...[cc-codex]` | **BLOCKED** (same) |

The tests run the real CLI: a task and a decision recorded under one host, a handover, resumed
under the other, the decision found in shared memory and a worker admitted for the same task under
the second host.
