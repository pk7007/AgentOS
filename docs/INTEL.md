# Organisational intelligence: `agentos intel`

Advice drawn from the ledger AgentOS already keeps: tasks and their dependencies, workers,
evaluations, evidence, budgets, memory and experiments. Every rule is plain counting and ranking,
written down below. Nothing here calls a model, spends money or admits a worker; admission stays
the only gate. All commands take `--json` and `--project PATH or ID`.

| Command | Question it answers | Rule |
| --- | --- | --- |
| `intel staffing [--objective ID]` | How many workers of which kind does the open work need? | Open tasks are grouped into dependency **waves**; the peak wave width times the workers each finished task needed (this project's history when it has 3 or more finished tasks, else all projects), capped at `max_concurrent`, less the workers already active on open tasks (`to_recruit`). Per capability: the best fully matching template, or a `factory propose` action for a gap |
| `intel route TASK [--template ID]` | Which model tier is the cheapest the work justifies? | Start from risk (low: small, medium: medium, high and critical: large); effort 5 or more: one tier up; 3+ evaluations failing 30% or more: one up; averaging 85+: one down for low and medium risk only. Project history first, all projects when it has fewer than 3. Relative cost 1 / 3 / 10. Advice only: the host chooses the model; with the paid-spend cap at 0 it says to use the host's included models |
| `intel context TASK [--budget N]` | What should a worker read first, within a token budget? | Memory matching any word of the task, ranked validated first, then failure lessons, then confidence, then relevance; duplicates (same text ignoring case and spacing) dropped; greedy fill to the budget, reporting the duplicate and left-out tokens. Tokens are estimated at 4 characters each |
| `intel skills [--min-uses N]` | Which checks are proven enough to become a skill? | A command cited as evidence in at least 3 different tasks graded 70+ and unflagged by an independent evaluator, that passes at least 2 times in 3 wherever it ran |
| `intel skill-create EVIDENCE_ID [--name]` | Make it a reusable skill | Writes `~/.agentos/skills/<project>/<name>/SKILL.md` and a validated procedural memory citing the evidence; refused below the bar (`not_enough_evidence`), over a different skill of the same name (`skill_exists`) or for a command that cannot be written safely (`unsafe_command`). Only this project's evidence counts |
| `intel org [--idle-days N]` | Where is the organisation wasteful or fragile? | Templates not recruited for 30 days; pairs sharing two thirds of their capabilities; a capability with 3+ open tasks and one provider (single point of failure); 5+ open tasks per provider (overloaded); departments with no open tasks |
| `intel failures [--min-count N] [--record]` | What keeps failing? | Failing evidence grouped by **signature** (the last error line with paths, quoted values, hashes and numbers removed), timeouts, a template's repeatedly weakest score in failing evaluations, capabilities whose tasks fail or are retried. `--record` saves each pattern once as failure memory |
| `intel compete TASK [--min-margin M]` | Which of several solutions to one task is best? | Every worker on the task whose template can write is a competitor, graded or not; read-only workers that nobody graded are judges. Mean of each solution's grades by judges: a grade by another competitor is discarded; a flag or failing cited evidence disqualifies; a lead under 2 points is `no_clear_winner` |
| `intel governance` | Do the core invariants hold? | Re-derived from the raw tables, not from the code that enforces them: audit chain, evaluator independence, evidence-backed acceptance, gated promotions, paid spend under the cap, slots under `max_concurrent`, challengers only on their trials, shared memory validated. Exit 5 on any violation |
| `intel forecast [--objective ID]` | What will the rest cost? | Remaining effort times agent runs and estimated tokens per effort unit of finished work; time as waves times the median task duration (first start to completion, from the audit log); warnings where a budget would run out. Paid spend projected at 0 |
| `intel profile` | What does this project's history say? | Task states and success rate, the best template per capability in this project, the top failure patterns and proven commands |
| `intel lessons [--min-projects N]` | Which lessons are ready to share across projects? | Validated project lessons in shareable layers that at least 2 projects reached on their own (same text ignoring case and spacing) and that are not shared yet |
| `intel share MEMORY_ID` | Share one | Writes a validated organisation-wide record citing every source record; refused when the lesson is not validated, not in a shareable layer, or not confirmed by enough projects |

## How each was evaluated

Each feature is tested against a ledger with a planted, known answer
(`tests/unit/test_intel.py`): the detector has to report what was planted and nothing else, and
every refusal is exercised. Examples: three independent tasks and a dependent review give two
waves and a peak of three; three failing runs with different numbers and paths collapse into one
signature, while a one-off failure is not reported; a competitor's own grade of a rival is
discarded; each of eight planted governance violations is caught, and a clean ledger passes; a
lesson validated in one project is refused until a second project validates it. The CLI is tested
end to end in `tests/integration/test_cli_intel.py`. An independent code review graded each
feature against fixed criteria; see the Phase 7 table in [reports/AUDIT.md](../reports/AUDIT.md).

## Limits

- The thresholds (3 evaluations, 85 points, 30% failures, two thirds overlap, 2-point margin) are
  chosen by hand, not calibrated on real outcomes.
- Token figures are character-count estimates; AgentOS cannot see a host's real token use.
- Model tiers are relative. Mapping a tier to a model name is the host's choice.
- Lessons are matched by normalised text, so the same idea worded differently is not matched.
- "Independently validated" means validated in different projects. If one person copies the same text
  into two projects and validates both, it counts; AgentOS cannot tell.
- Staffing and forecasts count running tasks at their full effort, and fall back to all projects'
  history when a project has fewer than 3 finished tasks (the output says which basis it used).
