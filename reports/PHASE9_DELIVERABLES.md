# V4.0 final deliverables

Where each deliverable the V4.0 brief asks for lives. Nothing here restates a result; each line points to
the evidence.

| Deliverable | Where |
| --- | --- |
| Original specification compliance matrix | [AUDIT.md](AUDIT.md): every criterion of the 41 domains (A to AO) with a status and the test that proves it, plus one table per V4.0 phase (1 to 8) mapping each requirement of the brief to evidence |
| Before-and-after audit | [PHASE9_SCORES.md](PHASE9_SCORES.md): baseline, re-grade 1 and re-grade 2 for all 213 criteria, by independent graders; the baseline alone is [PHASE9_BASELINE.md](PHASE9_BASELINE.md), the rubric [AUDIT_CRITERIA.md](AUDIT_CRITERIA.md) |
| Actual implementation changes | the git history of `main`; per phase, the "V4.0 Phase N" tables in [AUDIT.md](AUDIT.md) name the modules and tests added |
| Verified agent runtime evidence | [AUDIT.md](AUDIT.md), "V4.0 Phase 2: runtime hooks" (the live spawn-gate run on the second host) and "V4.0 Phase 6: Host integration"; [COMPATIBILITY.md](COMPATIBILITY.md) |
| Codex compatibility report | [COMPATIBILITY.md](COMPATIBILITY.md), first table. Live Codex sessions are **BLOCKED** (no quota) |
| Second host (`cc`) compatibility report | [COMPATIBILITY.md](COMPATIBILITY.md), second table |
| Self-improvement benchmark results | [AUDIT.md](AUDIT.md), "V4.0 Phase 5: Self-improvement engine" (champion against challenger, held-out cases, promotion, rejection, rollback, each with its test); `agentos bench run` / `bench history` for AgentOS's own operation timings |
| Workforce management evidence | [AUDIT.md](AUDIT.md), "V4.0 Phase 4: Agent Factory and workforce management"; [docs/WORKFORCE.md](../docs/WORKFORCE.md) |
| Security audit | [AUDIT.md](AUDIT.md), domain S (security), AH (evaluation integrity), AJ (compliance and external actions) and AO (supply chain); the tests under `tests/security/` and `tests/unit/test_architecture.py` |
| Regression results | the header of [AUDIT.md](AUDIT.md) (test count and branch coverage of the last full run); every push runs the suite in CI on Windows and Ubuntu with Python 3.11 and 3.12 (`.github/workflows/ci.yml`) |
| Criterion-by-criterion ratings | [PHASE9_SCORES.md](PHASE9_SCORES.md) |
| Remaining blockers | [PHASE9_SCORES.md](PHASE9_SCORES.md), "Every row below 9, grouped" (fixable, blocked by an external limit, host reasoning); [docs/LIMITATIONS.md](../docs/LIMITATIONS.md) |
| Installation and usage documentation | [README.md](../README.md); [docs/RUNBOOK.md](../docs/RUNBOOK.md), [docs/TROUBLESHOOTING.md](../docs/TROUBLESHOOTING.md), [docs/EXAMPLES.md](../docs/EXAMPLES.md), [docs/CLI.md](../docs/CLI.md), [docs/REASONS.md](../docs/REASONS.md), [docs/HOST_PROFILE.md](../docs/HOST_PROFILE.md) |

## Summary of the result

- 39 of 213 criteria are at 9 or above after two independent re-grades. The goal of 9 on every criterion
  was not reached; [PHASE9_SCORES.md](PHASE9_SCORES.md) gives the reason for every row below 9.
- 30 criteria are blocked by limits outside the code, chiefly that no live Codex session could be run
  (the account has no quota) and that the hosts expose no stop API or token usage to AgentOS.
- Defects found by the graders were fixed with tests; the last round of fixes (N1 to N11) has not been
  re-graded.
