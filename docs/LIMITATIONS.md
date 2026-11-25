# Limitations (version 0.1.0, slice 1)

What AgentOS does not do yet, or cannot do at all. Read this before relying on it.

## Enforcement depends on the host asking

AgentOS is a ledger and referee that the host session consults. A host that never calls
`agentos agent admit` can still start workers. Nothing blocks it in slice 1. The skill tells
the host to ask before every spawn, and every denial is audited, but this is cooperation, not
enforcement. Hooks that block host actions until AgentOS says yes are planned for slice 2.

## Owner confirmation trusts the console

Owner-only actions (raising limits, a paid budget above zero, retiring templates, restore,
lifting the emergency stop) ask for `I APPROVE <action>` to be typed at a real interactive
console. Agents run without one, so they cannot answer. But anyone, or any program, that can
type into a real console on this machine as this user can confirm. AgentOS has no passwords or
second factor. Protect the machine and user account.

## Usage numbers are estimates

AgentOS cannot see a host's real token counts or bills. Budgets count what the host *reports*
(`tokens_est`, `agent_runs`). They are labeled estimates everywhere. Paid spend is capped at $0
by default because AgentOS itself never makes paid calls.

## Heuristics are uncalibrated

The complexity score (`plan score`), the recruit ranking weights and the performance weights
are simple hand-picked formulas. They have not been checked against outcomes. Benchmarks that
would calibrate them are planned for slice 3. Treat their output as a starting point.

## Termination may be unconfirmed

AgentOS cannot stop a host's native worker process. Moving an instance to TERMINATED records
the intent. Unless the host confirms the worker really stopped (`--confirmed`), the instance is
shown as `TERMINATED (unconfirmed)`.

## Secret redaction is pattern-based

Memory, audit payloads and handovers are passed through redaction for common secret formats
(private keys, `sk-` keys, GitHub and AWS tokens, Slack tokens, `password=`-style values).
Secrets in other formats are not caught. Don't paste secrets into AgentOS.

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

Built and tested on Windows 11 with Python 3.11. The installer is PowerShell only. The Python
package has no Windows-only code apart from the console check, which falls back to `isatty()`
elsewhere, but other platforms are untested.

## Not in slice 1

Self-improvement experiments, champion/challenger promotion and benchmarks (slice 3); model
routing and predictive staffing (slice 4); blocking hooks (slice 2); a dashboard; any
background service. See `reports/AUDIT.md` for the criterion-by-criterion picture.
