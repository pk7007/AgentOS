# Host compatibility reports

Two hosts are supported: **Codex** and a second host, named `cc` in this repository. The second host's
vendor-specific paths live only in a git-excluded profile (`hosts/cc.local.toml`), so nothing pushed names
it. Each statement below says how it was verified: a test in CI, a live check on the owner's machine with
no model session, or a live session. Nothing is claimed that was not run.

## Codex compatibility report

| Capability | Status | How it was verified |
| --- | --- | --- |
| Generated plugin (skill, agents, hooks, marketplace entry) | VERIFIED | `agentos gen codex`; the committed plugin is checked against the definitions in CI: `unit/test_gen.py::test_committed_codex_plugin_is_up_to_date` |
| Plugin accepted by the real Codex CLI | VERIFIED (live, no session) | Codex 0.171.0, `codex plugin marketplace add` on the installed plugin in a throwaway `CODEX_HOME`: `live/test_host_compat.py::test_codex_accepts_the_installed_plugin` |
| Hooks discovered | VERIFIED (live, no session) | Codex 0.171.0 app-server `hooks/list` finds all three hooks with no errors: `integration/test_codex_hook_discovery.py` |
| Spawn gate, binding, stop handling (hook handler) | VERIFIED (tests) | `unit/test_runtime.py`: a spawn without an admitted ticket is refused, a stop is recorded, the emergency stop refuses every spawn |
| Install, update, drift, rollback, uninstall | VERIFIED | `agentos host install / drift / rollback / uninstall codex`: `unit/test_adapters.py`, `integration/test_cli_host.py` |
| Cross-host work through the ledger | VERIFIED | `integration/test_cli_host.py::test_work_and_learning_cross_hosts_both_ways` |
| Live Codex session following the skill | **BLOCKED** | `live/test_codex_smoke.py::test_codex_follows_skill` is written and marked `session`; it needs Codex model quota, which this account does not have. Run with `pytest -m session tests/live` once quota is available |
| Live spawn through the Codex hook | **BLOCKED** | same reason: needs a Codex model session |

## Second host (`cc`) compatibility report

| Capability | Status | How it was verified |
| --- | --- | --- |
| Generated plugin from a TOML profile | VERIFIED | `agentos gen host --profile`: `unit/test_gen.py`, `unit/test_adapters.py` |
| Plugin validated by the host's own validator | VERIFIED (live, no session) | the host's `plugin validate` passed with no warnings on the installed folder: `live/test_host_compat.py::test_the_second_host_validates_the_installed_plugin` |
| Spawn gate in a live session | VERIFIED (live) | 2026-11-26, in a throwaway AgentOS home: a spawn with no admitted instance was refused with AgentOS's reason; a spawn naming an admitted instance was allowed, bound to the runtime's agent id and moved to RUNNING (see the Phase 2 table in `reports/AUDIT.md`) |
| Coexistence with another installed plugin | VERIFIED (static) | `agentos host check cc`: hooks run alongside, same-named agents are namespaced, no duplicate AgentOS hooks: `unit/test_adapters.py::test_check_*` |
| MCP tools | VERIFIED (tests) | `agentos mcp serve` over stdio: `unit/test_ops.py::test_mcp_serves_over_stdio_in_a_real_process`; not yet connected from the host's MCP client |
| A full live session following the skill end to end | NOT RUN | would use the owner's model quota; not authorised in this phase |

## How to re-run the live checks

```powershell
.venv\Scripts\python -m pytest -m "live and not session" tests/live   # no model session, no quota
.venv\Scripts\python -m pytest -m session tests/live                    # uses Codex quota: owner's go-ahead first
```
