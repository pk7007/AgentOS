# Agent Factory and workforce management

`agentos factory` turns a capability gap into a specialist configuration and recruits it.
`agentos workforce` keeps the workforce matched to the work and to its record. Both work on the
ledger: they write configurations, statuses and records, and they never start or kill a host's
native worker. Admission stays the only way a worker becomes active, so limits, budgets, risk
rules and the emergency stop apply to everything here.

## Agent Factory

| Step | What happens |
| --- | --- |
| Detect | a task (or `--cap` list) whose capabilities no single active template fully covers. If one does, the factory refuses (`no_capability_gap`) and recruits that template instead |
| Propose | a draft is built from the **closest existing template** (best capability match, then performance) and inherits its tools, denied tools and read-only setting. With nothing similar, it starts read-only with no tools. Delegation is off and the security class is `standard`. The host may set fields from a TOML file (`instructions`, `description`, `tools_allow`, `tools_deny`, `read_only`, `reasoning_hint`, `model_hint`, `can_delegate`, `security_class`, `id`, `name`) |
| Validate | the five safety rules every AgentOS worker carries are appended if missing. Refused outright: text that loosens the rules ("ignore previous", "bypass", "without admission", ...), anything the secret redactor matches, instructions over 4000 characters, more than 8 capabilities, an id already in use, an invalid config, and more live factory specialists than `max_factory_templates` (default 5; raising it needs the owner) |
| Owner gate | a draft that asks for more than its base template (`write_access`, `new_tools`, `fewer_denied_tools`, `delegation`, `elevated_security`) is not registered until the owner grants the `factory_register` approval it requests (`agentos approval grant ID` at a real terminal). The approval is single use |
| Register | the template is added as version 1, active. It has no track record, so high-risk work still refuses it (`high_risk_unproven`) until it earns one |
| Recruit | `factory recruit` runs the steps above when needed and then **admission**, returning `admitted`, `awaiting_owner` or `denied` with reasons |
| Expire | temporary specialists (the default; 72 hours) are suspended once past their expiry, unless a worker is still active on them. Suspension keeps the configuration, its history and its evaluations. Retirement stays with the owner |

## Workforce management

| Responsibility | Command | Rule |
| --- | --- | --- |
| Performance-based candidate selection | `recruit`, `factory recruit`, `workforce transfer` | ranked on capability match, evaluated mean, reliability and confidence; high-risk work needs a proven template |
| Dynamic recruitment | `factory recruit` | see above |
| Temporary specialists | `factory propose`/`recruit` (default) | expire after `--ttl-hours`; `--permanent` to keep |
| Department creation and dissolution | `boss plan`, `workforce contract`, `boss deliver` | a department forms at 3 tasks of one function (2 for large objectives) and dissolves when none of its tasks is open; it can form again later |
| Workload-based multiplication | `workforce split TASK [--parts N]` | parts are capped by the task's `effort`, the free slots, `max_agents_per_task` and 8. The parent depends on every part and becomes the integration step; each part is admitted on its own |
| Recursive delegation | `agent admit --parent` | unchanged: only delegating templates, depth capped by `max_depth`; factory specialists don't delegate unless the owner approves |
| Workforce contraction | `workforce contract` | archives finished workers of closed tasks, expires temporary specialists, dissolves empty departments; idle or orphaned workers are reported, not stopped |
| Succession planning | `workforce succession` | every active template's ranked successors (templates covering all its capabilities), or `single_point_of_failure`, with how many open tasks only it covers |
| Rehabilitation | `workforce rehab TEMPLATE --file v2.toml`, `workforce probation TEMPLATE` | only for a weak template (retrain or retire-review recommendation, or a weak band). The new version may not widen permissions. After 3 evaluations of the new version: mean of 70 or more passes; under 50 fails and suspends; otherwise probation runs to 6 evaluations and fails under 70 |
| Performance-based suspension | `workforce review` | suspends on a retire-review recommendation (5 or more evaluations, mean under 50, two failing evaluators) or on 3 failing evaluations in a row; flags weak templates for rehabilitation; judges probation |
| Safe termination | `workforce terminate INSTANCE --reason --note` | an active worker is CANCELLED and keeps its slot until the host confirms the native stop; a finished one is TERMINATED. The note goes to project memory; evaluations, evidence and the audit trail stay |
| Automatic replacement and transfer | `workforce transfer INSTANCE --host [--to TEMPLATE] --note` | picks the best other covering template unless one is named, checks it would be admitted **before** stopping the old worker, then admits it and returns a briefing (task, previous worker's last reason, evaluations, evidence, the note) |

## Records

Migration `0005_workforce.sql` adds `factory_proposals`, `rehabilitations` and `transfers`.
Audit events: `factory.proposed`, `factory.awaiting_owner`, `factory.registered`,
`factory.register_denied`, `factory.rejected`, `factory.expired`, `workforce.reviewed`,
`workforce.rehab_started`, `workforce.rehab_rehabilitated`, `workforce.rehab_failed`,
`workforce.split`, `workforce.terminated`, `workforce.transferred`, `workforce.transfer_denied`
and `boss.department_dissolved`, alongside the template, agent and memory events they cause.

## Limits

- The factory drafts configurations by rule, not by model: the host writes better instructions
  with `--file` when it can. Validation checks a configuration is safe, not that it is good; the
  evaluations that follow are what show that.
- The thresholds (3 failures in a row, probation at 3 and 6 evaluations, 70 and 50, 72 hours,
  5 live specialists) are hand-picked and uncalibrated.
- AgentOS cannot stop a native worker. Terminate and transfer record the stop and tell the host
  what to stop; a cancelled worker keeps its slot until the stop is confirmed.
