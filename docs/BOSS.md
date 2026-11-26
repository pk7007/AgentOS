# The Boss loop

`agentos boss` runs one objective from statement to delivery. As everywhere in AgentOS, the
host's model does the thinking: it understands the objective, decomposes it, writes the code
and grades the work. AgentOS keeps the books and refuses what breaks the rules. Nothing here
calls a model, spends money or starts a worker on its own.

## What each responsibility maps to

| Responsibility | How AgentOS supports it |
| --- | --- |
| Objective understanding | `boss start` records title, statement and acceptance criteria; it refuses an objective with no testable criterion (`no_acceptance_criteria`) |
| Task complexity assessment | the eight `plan score` factors on `boss start` record a score and band on the objective |
| Dynamic task decomposition | `boss plan` applies the host's JSON plan in one transaction: titles, capabilities, acceptance, risk, priority, effort, parent and dependencies. A bad field, unknown dependency or cycle creates nothing |
| Dependency-aware scheduling | `boss next` orders ready tasks by critical path length, then priority, then age, and marks each `dispatch`, `queued_capacity`, `blocked_by_policy` or `capability_gap` using the same checks as admission |
| Department creation | a department forms for a function when 3 tasks of the objective share it (2 for `department` and `hierarchical` bands) |
| Specialist recruitment | each scheduled task names templates whose capabilities fully cover it, ranked by `recruit` |
| Recursive workforce expansion | for large bands only, a department with 3 or more ready tasks gets a suggested `lead` worker (a delegating template); admission still caps depth and concurrency |
| Resource allocation | free slots come from `limits`; `boss next` hands them out in schedule order and queues the rest |
| Bottleneck detection | `boss bottlenecks`: blocked or failed tasks, open tasks that 2 or more others wait on, capability gaps, done but unaccepted tasks, workers the runtime reports stopped, workers silent for 60 minutes, full capacity, budgets 80% used |
| Independent quality control | `boss accept` needs an evaluation of a worker on that task, by an independent evaluator (enforced by `eval record`), weighted 70 or more, unflagged, citing evidence whose command exited 0 |
| Failure recovery | `boss recover` sends a failed task back to pending with the templates that failed it to avoid and a suggested other one, or, once retries are spent, says `escalate_owner` |
| Final delivery | `boss deliver` needs every task done or cancelled, every done task accepted and one passing `evd_` record per acceptance criterion; it writes a report and closes the objective |

## The nine executive functions

`boss review` runs operations, engineering, hr, finance, intelligence, security, data, risk
and quality as **checks over the ledger**, each `ok` or `attention` with findings:

| Function | Looks at |
| --- | --- |
| operations | task progress and flow bottlenecks |
| engineering | task count, departments, open tasks without acceptance criteria |
| hr | active workers by template, capability gaps |
| finance | budgets close to their limit |
| intelligence | related project memories |
| security | flagged evaluations, emergency stop |
| data | done tasks with no graded evidence |
| risk | open high or critical tasks, exhausted retries |
| quality | done tasks not yet accepted |

None of these starts a worker. Routine objectives get no executive workers at all.

## Plan file

```json
{"tasks": [
  {"key": "api", "title": "add export endpoint", "capabilities": ["implementation"],
   "acceptance": ["endpoint returns CSV"], "risk": "low", "priority": 70, "effort": 2},
  {"key": "docs", "title": "document export", "capabilities": ["documentation"],
   "depends_on": ["api"], "department": "operations"}
]}
```

`key` and `title` are required. `depends_on` takes keys from the same plan or task ids already
in the objective; a task of another objective is refused (`cross_objective`). `department` must
be one of the nine functions; without it the function is inferred from the capabilities, and
defaults to engineering. A later `boss plan` can add tasks to the same open objective.

## Records

Migration `0004_boss.sql` adds `objectives`, `departments` and `task_acceptances`, and the
`objective_id`, `department` and `effort` columns on `tasks`. Every step is in the audit log:
`boss.objective_created`, `boss.plan_applied`, `boss.department_created`, `boss.task_accepted`,
`boss.acceptance_denied`, `boss.recovery`, `boss.escalated`, `boss.delivery_denied` and
`boss.delivered`.

## Limits

The thresholds above (3 tasks per department, 60 minutes stale, 80% budget, score 70) are
hand-picked and uncalibrated, like the complexity score. The schedule is advice: a host can
still admit tasks in another order, and admission remains the gate.
