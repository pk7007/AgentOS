# How the audit is scored

This file was written before any criterion was graded. It defines what each score means, so a number
in `reports/AUDIT.md` can be checked against the evidence cited next to it. Scores are never averaged:
every criterion keeps its own score, and the lowest scores are listed first in the summary.

## The scale

Each criterion of the 41 V4.0 domains gets one whole number from 0 to 10.

| Score | Meaning | What must be true |
| --- | --- | --- |
| 10 | Complete | Built; an automated test checks the behaviour and at least one refusal or failure case; documented; nothing in AgentOS's scope is left open. |
| 9 | Complete with a stated limit | As for 10, but one limit is written down (in the row and in `docs/LIMITATIONS.md`), and the limit does not stop the criterion doing its job. |
| 8 | Built, part unproven | Built and tested, but a material part is not proven: the test has no refusal case, the figures are estimates, or the proof is local only. |
| 7 | Built, gap | Built and tested, with a gap a user would notice (a missing option, a manual step that should not be needed). |
| 5–6 | Partial | Part of the criterion is built and tested; a significant part is missing. |
| 3–4 | Unproven | Built but not tested by an automated test, or only described in documentation. |
| 1–2 | Designed | Only a design or a stub exists. |
| 0 | Missing | Nothing exists. |

## Rules the grader follows

1. **Evidence first.** A score of 7 or more needs a test the grader has found in `tests/` and seen
   pass in the regression run. A cited test that does not exist caps the row at 4.
2. **Refusal cases.** 9 and 10 need a test that shows the feature refusing, failing safely or
   detecting a fault, not only the happy path.
3. **No reinterpretation.** A mandatory capability that is missing is scored as missing. Saying it is
   "the host's job" does not raise the score: the criterion is graded on what the whole system,
   AgentOS plus a host, has been shown to do.
4. **Blocked is not passed.** When a criterion can only be proven with something that is not
   available (for example a live model session on a host whose quota is spent), the row is marked
   `BLOCKED`, the score covers only what was proven, and the reason is written in the row.
5. **Independent grading.** The grader is not the author of the change being graded. A grader reads
   the code, the tests and the regression output; it does not take the author's word.
6. **No averages.** There is no overall score. The summary lists how many criteria sit at each score
   and names every criterion below 9.
7. **Re-grading.** A criterion that is fixed is graded again by a grader that did not make the fix,
   and both the old and the new score are kept in the before-and-after table.
