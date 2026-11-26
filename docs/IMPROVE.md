# Self-improvement

`agentos improve` lets the system get better from its own record without letting it change itself
unchecked. A change to how work is done replaces nothing until it beats the current way of doing
it (the **champion**) on fixed benchmark cases, graded independently, after the regression and
security checks pass. It is then watched, and rolled back if it regresses.

AgentOS never calls a model, so it cannot write a better prompt by itself. Its hypotheses are
rule-based (from what the record shows), and the host can propose its own. What AgentOS does is
make sure a change *earns* promotion.

## The loop after each piece of work

| # | Step | How |
| --- | --- | --- |
| 1 | Collect outcomes, measurements and evidence | `improve retro` (run automatically by `boss accept` and `boss deliver`) gathers task states, retries, every evaluation and whether its evidence passed |
| 2 | Identify successful and unsuccessful strategies | per worker: successful = mean ≥ 85, passing evidence, task done; unsuccessful = mean < 70, failing evidence or failed task |
| 3 | Diagnose recurring weaknesses | a template sub-score averaging < 70 over ≥ 3 evaluations; evidence failing in half or more of a template's grades; an admission refusal reason seen ≥ 3 times; a capability whose tasks failed ≥ 2 times |
| 4 | Generate hypotheses | a weak sub-score maps to a concrete instruction addendum for that template; recurring `capability_mismatch` maps to raising the recruitment weight on capability match. A change already tried, or a target with a running experiment, is not proposed again |
| 5 | Propose an improved configuration | `improve propose --from-retro`, or `--template ID --file changes.toml`, or `--policy NAME --value N` |
| 6 | Create an isolated candidate | the challenger is stored as a separate template with status `candidate` (`<target>-c<n>`). Recruitment never sees it, and admission accepts it only on its own experiment's trial tasks while that experiment runs |
| 7 | Evaluate against the baseline | for every case, both arms run on their own trial task: `improve trial`, then `improve check` (AgentOS runs the case's command), then an independent grade attached with `improve score` |
| 8 | Representative and held-out cases | at least 3 representative and 2 held-out cases must be paired. Held-out cases are shown by id and hash only |
| 9 | Security and regression tests | `improve gate EXP -- <command>`: the latest gate run must pass. At decision time the challenger is re-checked: same safety validation as the Agent Factory, and no wider access than the champion |
| 10 | Independent evaluation | the grade must be for the trial's worker, cite the evidence AgentOS recorded for that case, and come from an evaluator whose template is neither arm. Two or more distinct evaluators are required. Trials are labelled A/B so graders needn't know which arm they grade |
| 11 | Promote validated improvements | `improve decide`: representative mean gain ≥ 2 points with more wins than losses, no loss on held-out cases, no fewer cases passing their check, nothing flagged. A template change becomes a new version of the champion (permissions untouched); a policy change is written to settings |
| 12 | Reject ineffective changes | otherwise the experiment is rejected with the reasons, and a failure memory records the numbers so it is not retried blindly |
| 13 | Monitor | `improve monitor` (also run by every retro) waits for 5 grades of the new version (for a policy: project grades after promotion) |
| 14 | Roll back regressions | a mean more than 5 points below the champion's trial baseline restores the previous version or value, marks the experiment `rolled_back` and records why |
| 15 | Preserve validated learning | a promotion writes a validated, organization-wide procedural memory with the hypothesis and the numbers; later sessions find it with `memory search` |

## What can change, and what cannot

| May change through an experiment | Can never change through one |
| --- | --- |
| a template's `instructions`, `description`, `reasoning_hint`, `model_hint` | capabilities, tools, denied tools, read-only, delegation, security class |
| the recruitment weights `recruit.w_match`, `w_history`, `w_reliability`, `w_confidence`, each within fixed bounds (`improve policies`) | limits, budgets, approvals, owner-only actions, ownership, the audit log, emergency stop |

A field outside the left column is refused (`not_tunable`); a value outside its bounds is refused
(`out_of_bounds`). Replacing a working template by hand (`template add` with an existing id) now
needs the owner, so the experiment path cannot be side-stepped.

Through the left column the system improves its own recruitment decisions (the weights), staffing
and task planning (the lead and planner instructions), skills (validated procedural memory) and
context handling (instructions on what to read and report). Its security boundaries are not in
reach.

## Guarding the measurement

| Risk | Guard |
| --- | --- |
| Benchmark leakage | held-out cases are hidden from listings and the audit log (hash only). A challenger whose text shares a 6-word run with a held-out case, or contains its title, is refused (`benchmark_leakage`). A held-out case used by an earlier experiment counts as representative from then on |
| Moving the goalposts | cases added after the experiment started don't count (`case_after_experiment`); a case is stored with a content hash |
| Grading your own side | evaluators of either arm's template are refused (`evaluator_not_independent`); performance rules still forbid self, parent and child grading |
| Invented results | the grade must cite the evidence AgentOS recorded by running the case's own command (`evidence_not_from_case`) |
| Dropping bad trials | a trial whose worker ended without a grade counts as a score of 0 and a failure |
| Champion edited mid-experiment | trials refuse to start (`champion_changed`); a hand edit after promotion ends monitoring as `superseded` |
| Self-promotion | promotion happens only in `improve decide`, on the rules above; there is no flag that skips them |

## Commands

```
agentos improve retro [--task T | --objective O | --show RETRO]
agentos improve case --suite S --title T --split representative|heldout [--cap C] [--accept A] -- COMMAND...
agentos improve cases [--suite S]
agentos improve propose --suite S (--from-retro R [--index N] | --template ID --file F | --policy NAME --value N) [--hypothesis H]
agentos improve trial EXP CASE --arm champion|challenger --host H
agentos improve check TRIAL
agentos improve score TRIAL EVAL
agentos improve gate EXP -- COMMAND...
agentos improve status | decide | show EXP
agentos improve abandon EXP --reason R
agentos improve monitor
agentos improve experiments [--status S]
agentos improve policies
```

Experiment states: `trialing` → `promoted` → `adopted` | `rolled_back` | `superseded`, or
`trialing` → `rejected` | `abandoned`.
