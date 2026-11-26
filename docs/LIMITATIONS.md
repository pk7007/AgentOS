# Limitations (version 0.1.0, slice 1)

What AgentOS does not do yet, or cannot do at all. Read this before relying on it.

## Enforcement needs the runtime hooks

Without hooks, AgentOS is a ledger the host consults: a host that never calls
`agentos agent admit` can still start workers. With the Codex plugin's hooks trusted, Codex
itself asks AgentOS before every `spawn_agent` call and refuses spawns that have no admitted
instance. What that still doesn't cover:

- Hooks run only after the owner trusts them, and Codex skips a hook whose content changed until
  it is trusted again. Hosts without hooks are back to cooperation.
- A subagent started some other way is not seen at spawn time. When it starts, AgentOS records
  it (`runtime.unadmitted_subagent`) and tells it to stop, but Codex doesn't let that hook block.
- The gate picks the project from the `cwd` the runtime reports.
- Verified so far: Codex CLI 0.171.0 discovers the three hooks from the plugin (its app-server
  `hooks/list`, no model call), and the handler follows the documented hook protocol in tests. A
  live session spawning a real subagent through the hook has **not** been run yet; it needs the
  owner's go-ahead because it uses quota.
- Second host (`cc`): checked live on 2026-11-26 with version 2.1.331, in a throwaway AgentOS home: a spawn with no admitted instance was refused with AgentOS's reason; a spawn naming an admitted instance was allowed, bound to the runtime's agent id and moved to RUNNING, and its stop was recorded; `audit verify` passed. That host sent SubagentStop twice for one subagent
  (handled), and reports the parent's `session_id` for a subagent. A subagent's tool calls carry
  its `agent_id` there and the main session's don't, so `--guard-tools` can tell them apart.

## Owner confirmation trusts the console

Owner-only actions (raising limits, a paid budget above zero, retiring templates, restore,
lifting the emergency stop) ask for `I APPROVE <action>` to be typed at a real interactive
console. Agents run without one, so they cannot answer. But anyone, or any program, that can
type into a real console on this machine as this user can type the phrase, which the prompt
shows. Set an owner PIN (`agentos owner pin set`) so a confirmation also needs a secret the
prompt never shows. Anything that can write the database file directly is outside this
protection. Protect the machine and user account.

## Usage numbers are estimates

AgentOS cannot see a host's real token counts or bills. Budgets count what the host *reports*
(`agent_runs` at admission, `tokens_est` and `usd` through `agentos budget use`). A host that
never reports usage is never charged. They are labeled estimates everywhere. Paid spend is capped at $0
by default because AgentOS itself never makes paid calls.

## Heuristics are uncalibrated

The complexity score (`plan score`), the recruit ranking weights and the performance weights
are simple hand-picked formulas. They have not been checked against outcomes. Benchmarks that
would calibrate them are planned for slice 3. Treat their output as a starting point.

## The Boss loop advises; admission decides

`agentos boss` keeps the plan, schedule and quality gate for an objective. Its thresholds (3
tasks per department, 60 minutes before a worker counts as stale, 80% budget warning, score 70
to accept) are hand-picked and uncalibrated. The nine executive functions are checks over the
ledger, not agents, and the schedule is advice: a host can admit tasks in another order, and
admission stays the gate. Decomposition quality is the host's; AgentOS checks only that the
plan is well formed.

## Termination may be unconfirmed

AgentOS cannot stop a host's native worker process. Moving an instance to CANCELLED or
TERMINATED records the intent. Until the host confirms the worker really stopped
(`agent confirm-stop`, or `--confirmed`), the instance keeps its concurrency slot and shows as
`TERMINATED (unconfirmed)`. If a host crashes without confirming, the owner or a later session
must confirm the stop to free the slot. With the runtime hooks on, the runtime's own
SubagentStop event confirms it. AgentOS still cannot kill a running subagent; with
`hook config --guard-tools` its tool calls are refused once it is cancelled, but only if the
runtime identifies the subagent on those calls: the second host (`cc`) does (seen live), Codex is
unverified.

## Secret redaction is pattern-based

Memory, audit payloads, evidence output and handovers are passed through redaction for common
secret formats (private keys, `sk-`, GitHub, GitLab, npm, AWS, Slack, Stripe and Google keys,
JWTs, `Bearer` tokens, passwords in URLs, and `password` / `*_secret` / `*_key`-style values,
including JSON). Secrets in other formats are not caught. Don't paste secrets into AgentOS.

## Evidence proves what ran, not what it means

`agentos evidence run` records the real exit code and output of a command AgentOS ran itself,
so a result can't be invented. A host can still choose a command that proves nothing; the
record shows the exact command, so reviewers should read it.

## Evaluator identity is not authenticated

An evaluator must be a registered agent instance of the same project, but AgentOS has no
per-agent credentials, so a host that knows another instance's id can grade under it.

## Search is keyword search

Memory search uses SQLite FTS5 keyword matching. There are no embeddings, so different wording
for the same idea may not match.

## Hosts

- **Codex:** the generated plugin installs and enables in Codex CLI 0.171.0 (checked in a
  throwaway `CODEX_HOME`). A live Codex session following the skill end to end has **not** been
  run yet. `tests/live/test_codex_smoke.py` does that, and runs only with `pytest -m live` and
  the owner's go-ahead, since it uses the signed-in account's quota.
- **Other hosts:** `agentos gen host` writes plugin files from a profile
  ([HOST_PROFILE.md](HOST_PROFILE.md)). Whether a given host loads them is unverified until
  someone checks with that host's CLI.

## Platform

Built on Windows 11 with Python 3.11. The installer is PowerShell only. The Python package has
no Windows-only code apart from the console check, which falls back to `isatty()` elsewhere.
CI (`.github/workflows/ci.yml`) runs lint and the test suite on Windows and Ubuntu with Python
3.11 and 3.12, and passes there; macOS is untested.

## Not in slice 1

Self-improvement experiments, champion/challenger promotion and benchmarks (slice 3); model
routing and predictive staffing (slice 4); a dashboard; any
background service. See `reports/AUDIT.md` for the criterion-by-criterion picture.
