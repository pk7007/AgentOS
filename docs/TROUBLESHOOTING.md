# Troubleshooting and debugging

## Reading a refusal

Every refusal exits with code `3` and lists machine-readable reasons. With `--json` the reasons are in
`stderr` as `{"error": ..., "exit_code": 3, "reasons": [...]}`.

| Exit code | Meaning |
| --- | --- |
| 0 | ok |
| 2 | usage error, or AgentOS is not initialized |
| 3 | refused by policy; see `reasons` |
| 4 | not found |
| 5 | integrity failure (audit chain, schema newer than this AgentOS) |

The table below covers the reasons people meet most. Every reason AgentOS can give, where it is raised
and its message, is in [REASONS.md](REASONS.md), generated from the source (a test fails if it falls
behind).

| Reason | What it means | What to do |
| --- | --- | --- |
| `max_concurrent` | every worker slot is taken | wait, or confirm stopped workers (`agentos agent confirm-stop <id>`) |
| `project_max_concurrent` | this project's own slot limit is reached | `agentos policy show`; loosening it is owner-only |
| `capability_mismatch` | the template lacks a capability the task needs | `agentos recruit --cap <capability>`, or `agentos factory propose --cap <capability>` |
| `duplicate` | the same template already works on this task | use the running worker |
| `path_claimed` | another active worker holds that path | message it (`agentos msg send --from <you> --to <holder> <text>`), or wait; a claim of a dead worker is freed automatically |
| `not_active` | the worker is not in an active state | check `agentos agent inspect <id>` |
| `self_evaluation` | a worker, its parent or child tried to grade it | use an independent reviewer |
| `unverified_evidence` | an evaluation cites no `evd_` record | run the check through `agentos evidence run -- <command>` |
| `cross_project` | the record belongs to another project | run from its repository, or pass `--project` |
| `owner_required` | only the owner may do this | run it yourself in a terminal |
| `not_delivered` | a workflow can only be taken from a delivered objective | deliver it first, or `agentos workflow save <name> --file <plan.json>` |
| `tampered` | a stored workflow no longer matches its hash | restore from a backup |
| `retry_limit` | the task was retried as often as allowed | re-plan it, or raise its limit (owner) |

## Debugging what happened

* `agentos audit log --limit 50` shows the last events with who did what; `--kind agent.admission_denied`
  narrows it.
* `agentos observe incidents` lists refusals and security events, most severe first.
* `agentos observe spans` gives one span per worker, from admission to the moment it stopped, grouped into
  traces by the root worker; `agentos observe timeline --days 14` shows activity per day.
* `agentos policy history` lists every change to limits, budgets and the emergency stop, with who made it.
* `agentos agent inspect <id>` shows one worker's state, parent and last reason.
* `agentos intel governance` re-checks the core invariants from the raw ledger and exits 5 on a violation.
* `agentos doctor` checks the installation and which host CLIs are on PATH.

## Common problems

| Symptom | Fix |
| --- | --- |
| `agentos` is not recognized | open a new terminal after installing; check `%USERPROFILE%\.agentos\bin` is on PATH |
| `not initialized; run: agentos init` | run `agentos init` |
| `database schema vN is newer than this AgentOS` | install the newer AgentOS; never downgrade a database |
| hooks never run in the host | trust them in the host's hook settings; check `agentos --version` in a new terminal |
| `agentos mcp serve` exits at once | it serves over stdin; start it from an MCP client, not by hand |
| a test of the generated files fails | run `agentos gen codex --force`, `agentos gen schemas` and `agentos gen docs` |
