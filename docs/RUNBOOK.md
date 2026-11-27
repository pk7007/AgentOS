# Recovery runbook

What to do when something goes wrong, in the order to try it. Every step is a command you run in a normal
terminal; the ones marked *owner* ask you to type `I APPROVE <action>`.

## Before anything else: take a backup

```powershell
agentos backup
```

The copy lands in `%USERPROFILE%\.agentos\backups\`. A backup is a consistent SQLite snapshot even while
agents are working. Keep the latest few; a restore always keeps a safety copy of the database it
replaces, so a restore can itself be undone.

## Upgrading to a new version (schema migrations)

1. `agentos backup`
2. Install the new version (`scripts\install.ps1`, or `pip install -e .` in a checkout).
3. `agentos init` applies each pending migration in its own transaction, in order. A failed migration is
   rolled back and stops the upgrade; the migrations before it stay applied (`unit/test_architecture.py`
   checks both), so the database is always at one whole schema version. Restore the backup from step 1 if
   you need the old version back.
4. `agentos audit verify` must report `ok`.

If step 3 or 4 fails: `agentos restore <backup>` (*owner*), reinstall the previous version and report the
error. A newer database is never opened by an older AgentOS: it refuses with exit 5 instead of guessing.

## The audit chain is broken (`audit verify` exits 5)

The database was changed outside AgentOS. The result names the first bad event and why.

1. Stop new work: `agentos stop --reason "audit chain broken"`.
2. Save the evidence: copy `%USERPROFILE%\.agentos\state\agentos.db` somewhere safe.
3. Find the newest backup that verifies: `agentos restore <backup>` (*owner*), then `agentos audit verify`.
   Repeat with an older backup if it fails.
4. Compare the saved copy with the restored one to see what was changed, then lift the stop
   (`agentos stop --lift`, *owner*).

An anchor (`agentos audit anchor --out FILE`, kept outside the machine) proves a restored chain is the one
you had: `agentos audit verify --anchor FILE`.

## A worker went silent

```powershell
agentos health stale --after-minutes 15
agentos health reap --after-minutes 15
```

`reap` marks each silent worker FAILED (CANCELLED if it never started), frees its slot, and either puts its
task back to pending for a retry with a different template or, at the retry limit, escalates it to you.
Check `agentos dashboard` afterwards. If the host's worker is still running somewhere, stop it in the host,
then `agentos agent confirm-stop <id>`.

## Admission is refused although nothing seems to run

* `max_concurrent`: a CANCELLED or unconfirmed TERMINATED worker still holds a slot. Once the worker is
  really gone: `agentos agent confirm-stop <id>`.
* `project_max_concurrent`: this project has its own lower limit (`agentos policy show`).
* `emergency_stop`: someone pressed stop. `agentos observe incidents` says who and why; lifting it is
  *owner*.
* The template is suspended: a circuit breaker or a performance review suspended it.
  `agentos observe incidents` shows `health.breaker_tripped`; review the evaluations
  (`agentos perf show <template>`) before re-activating it (`agentos template reinstate <template> --reason x`).

## The database is locked or slow

AgentOS waits up to 10 seconds for a busy database instead of failing. If commands still time out, another
process holds a write transaction: close stray `agentos` processes. `agentos bench run --n 50` measures the
core operations on a scratch database, and `agentos bench history` shows whether they have slowed down.

## A host plugin is broken after an update

```powershell
agentos host drift codex
agentos host rollback codex
```

`rollback` restores the previous install from its own backup and records it.

## Disk usage

`agentos retention plan --days 90` counts read messages, old benchmark runs and deleted memory that can go;
`agentos retention apply --days 90` removes them (*owner*). The audit log is never pruned.
