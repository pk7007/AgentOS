# Worked examples

Each example runs from the repository you are working in, after `agentos init`, `agentos template seed`
and `agentos project activate .`. Add `--json` to any command to get machine-readable output.

## Two workers on one change without stepping on each other

```powershell
agentos task add "Add rate limiting"
agentos agent admit --task <task> --template implementer --host codex
agentos agent admit --task <task> --template reviewer --host codex
agentos claim take <implementer> src/api/limits.py tests/test_limits.py
agentos claim take <reviewer> src/api            # refused: path_claimed, names the holder
agentos msg send --from <implementer> --to <reviewer> --kind request "ready for review"
agentos msg inbox <reviewer> --mark-read
agentos claim release <implementer>
```

## Asking the owner for a decision

```powershell
agentos msg escalate --from <worker> --task <task> "the spec and the tests disagree on the limit"
agentos dashboard                                 # shows ESCALATIONS waiting for the owner
agentos msg inbox owner --mark-read
```

## Reusing a plan that worked

```powershell
agentos workflow from-objective <delivered-objective> api-feature
agentos boss start "Second API feature" --accept "tests pass"
agentos workflow apply <new-objective> api-feature
```

## Choosing a worker and a model tier

```powershell
agentos intel options <task>        # expected score, 90% interval, relative cost, risks; or insufficient_evidence
agentos intel route <task> --host codex
agentos intel context <task> --budget 800 --record
```

## Keeping workers alive and recovering silent ones

```powershell
agentos health heartbeat <worker>   # the host reports this while the worker runs
agentos health stale --after-minutes 15
agentos health reap --after-minutes 15
```

## Tightening one project

```powershell
agentos policy project-limit max_concurrent 2
agentos policy show
agentos policy history
```

## Measuring AgentOS itself

```powershell
agentos bench run --n 100
agentos bench history
```

## Connecting an MCP client

Point the client at the command `agentos mcp serve` (stdio). It offers read-only tools: status, the
dashboard, every `observe` view, memory search, routing advice, the policy and the governance check.
