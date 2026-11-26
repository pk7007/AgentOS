# AgentOS audit: slice 1 (core ledger and CLI)

Criterion register over the source spec's audit domains A to AO, for version 0.1.0.

## How to read this

| Status | Meaning |
| --- | --- |
| **VERIFIED** | An automated test or a command run during this slice proves it. Evidence names the test. |
| **PARTIAL** | Part of it is proven. The note says which part is not. |
| **UNVERIFIED** | Something exists for it, but nothing proves it works. |
| **BLOCKED** | Needs something not available yet, such as a live run that needs the owner's go-ahead. |
| **LATER (slice N)** | Not built in slice 1. The design assigns it to slice N. |
| **NOT BUILT** | Not built and not yet assigned to a slice. |

**No numeric scores and no average.** A number without a calibrated rubric would be invented,
which criterion Z forbids. The spec's 9/10 target is therefore **not claimed** for this slice.
A row is VERIFIED only when a test or recorded command shows it.

Evidence paths are relative to `tests/`. Test run at time of writing (after the V4.0 Phase 1
defect fixes): `python -m pytest -q` gives **381 passed** (the live test is excluded by default).
Branch coverage is 94% overall: admission 96%, audit 97%, evidence 95%, governance 97%, governor 96%, lifecycle 97%, performance 95%, redact 100%. `ruff check src tests` is clean. A fresh clone of the pre-fix commit `1b7d492` gave
303 passed and a clean ruff run, which is the Phase 0 baseline.

### Host role

AgentOS is the ledger and referee. The host session (Codex, or the second host `cc`) plans,
writes code and decides. Rows about the host's thinking (B, I, M, AM) are therefore mostly
about what AgentOS *records and enforces*, not about decision quality, which slice 1 cannot measure.

---

## A: Architecture

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Modularity | VERIFIED | one module per concern under `src/agentos/`; each has its own unit test file | 18 core modules, a 4-file generator package, 12 CLI command modules |
| Extensibility | PARTIAL | `cli/__init__.py` `COMMAND_MODULES`; `gen/host.py` profiles (`unit/test_gen.py::test_host_generate_uses_profile`) | adding a command or host needs no core change; no plugin API for third parties |
| Separation of concerns | VERIFIED | CLI handlers call core functions only; core never imports `cli` | the owner prompt lives in `governance` |
| Dependency boundaries | VERIFIED | `pyproject.toml`: one runtime dependency (pydantic) | stdlib for SQLite, TOML, argparse |
| Architectural simplicity | VERIFIED | no daemon, no network, no model calls; one SQLite file | |
| Configuration design | PARTIAL | limits and budgets in the DB (`unit/test_governor.py`); host profiles in TOML | no config file for the CLI itself |
| Documentation | PARTIAL | `README.md`, `docs/HOST_PROFILE.md`, `docs/LIMITATIONS.md`, design spec and plan | no API reference |

## B: Boss agent

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Objective understanding | NOT BUILT | none | the host does this; AgentOS stores the objective on tasks and handovers |
| Planning | PARTIAL | `plan score`: `unit/test_complexity.py`, `integration/test_cli_task.py::test_plan_score_cli` | a heuristic sizing aid, uncalibrated |
| Decision-making | NOT BUILT | none | host's job |
| Delegation | VERIFIED | `unit/test_admission.py::test_depth_and_delegation`, `::test_parent_must_be_active` | only `can_delegate` templates may spawn children |
| Coordination | PARTIAL | task dependencies and `task ready`: `unit/test_tasks.py::test_ready_orders_by_priority` | no messaging between agents |
| Accountability | VERIFIED | every state change is audited: `unit/test_lifecycle.py::test_illegal_transition_audited`, `unit/test_admission.py::test_denial_is_audited` | |
| Escalation | PARTIAL | owner-only actions refuse without the owner: `security/test_owner_guard.py` | no automatic escalation path |

## C: Corporate hierarchy

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Clear authority | VERIFIED | owner vs host split: `unit/test_governance.py::test_cannot_forge_confirmation`, `security/test_owner_guard.py::test_no_env_var_bypass` | |
| Role separation | VERIFIED | read-only reviewer and researcher templates; no self-grading: `unit/test_performance.py::test_self_eval_rejected`, `::test_parent_and_child_eval_rejected` | |
| Dynamic departments | NOT BUILT | templates carry a `department` field only | |
| Managerial effectiveness | NOT BUILT | none | not measurable in slice 1 |
| Organizational adaptability | LATER (slice 3) | none | needs benchmarks |

## D: Dynamic recruitment

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Capability detection | VERIFIED | `unit/test_recruit.py::test_gap_reported`; `integration/test_cli_flows.py::test_eval_perf_and_recruit` | reports missing capabilities, never invents a template |
| Candidate selection | VERIFIED | `unit/test_recruit.py::test_rank_prefers_match`, `::test_rank_prefers_history_on_equal_match`, `::test_high_risk_requires_proven` | weights uncalibrated |
| Onboarding | PARTIAL | `template add` / `seed`: `unit/test_templates.py::test_seed_definitions_load`, `integration/test_cli_template_file.py` | no probation step |
| Validation | PARTIAL | schema validation of templates (`unit/test_templates.py::test_bad_slug_rejected`) | no behavioural validation of a new template |
| Recruitment efficiency | NOT BUILT | none | not measured |

## E: Elastic workforce scaling

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Recursive delegation | VERIFIED | `unit/test_admission.py::test_depth_and_delegation` | depth capped by `max_depth` (default 2) |
| Concurrency | VERIFIED | `concurrency/test_parallel_admission.py::test_parallel_processes_never_exceed_limit` | 12 processes race; exactly 4 admitted |
| Workload adaptation | PARTIAL | complexity band suggests agent count (`unit/test_complexity.py::test_parallelism_caps_agents`) | advisory only |
| Overhead management | PARTIAL | `max_agents_per_task`: `unit/test_admission.py::test_max_agents_per_task` | |
| Workforce contraction | VERIFIED | slots free on leaving active states: `unit/test_admission.py::test_release_on_completion` | |

## F: Firing and replacement

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Performance diagnosis | VERIFIED | `unit/test_performance.py::test_bands_and_retain`, `::test_critical_visible_despite_high_mean`, `::test_external_cause_excluded` | |
| Rehabilitation | PARTIAL | `retrain` recommendation and RETRAINING state exist (`unit/test_lifecycle.py`) | no retraining procedure |
| Suspension | VERIFIED | `unit/test_templates.py::test_suspend_and_reinstate_without_owner`, `integration/test_cli_flows.py::test_template_status_verbs` | |
| Safe cancellation | PARTIAL | CANCELLED then TERMINATED, recorded as unconfirmed: `unit/test_lifecycle.py::test_terminate_unconfirmed_is_recorded` | AgentOS cannot stop a host's native worker; see LIMITATIONS |
| Replacement | PARTIAL | `retire_review` needs 5 or more evaluations from 2 or more failing evaluators: `unit/test_performance.py::test_retire_review_needs_two_evaluators`; retire needs the owner | no automatic replacement |
| Knowledge preservation | PARTIAL | memory and handovers survive retirement (`unit/test_memory.py`, `unit/test_handover.py`) | no exit-interview capture |

## G: Governance

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Owner authority | VERIFIED | `unit/test_governance.py::test_cannot_forge_confirmation`, `unit/test_governor.py::test_raise_limit_needs_owner`, `unit/test_templates.py::test_retire_requires_owner`, `integration/test_cli_system.py::test_restore_without_owner_denied` | owner types `I APPROVE <action>` at a real console |
| Approval requirements | VERIFIED | `unit/test_governance.py::test_approval_bound_to_params`, `::test_approval_single_use`, `::test_approval_expires`; `unit/test_governance_edges.py::test_deny_granted_approval_is_refused_and_not_audited` | |
| Policy enforcement | PARTIAL | admission refuses with every reason: `unit/test_admission.py::test_all_reasons_collected` | **enforcement relies on the host asking**; blocking hooks are slice 2 |
| Emergency controls | VERIFIED | `unit/test_governance.py::test_stop_blocks_admission_but_allows_winddown`, `integration/test_cli_flows.py::test_emergency_stop_blocks_admission_and_lift_needs_owner` | |
| Independent oversight | VERIFIED | evaluator independence: `unit/test_performance.py::test_parent_and_child_eval_rejected` | |

## H: Self-healing

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Failure detection | PARTIAL | FAILED state, retry limit: `unit/test_tasks.py::test_retry_limit`; orphan warnings on resume: `unit/test_handover.py::test_orphaned_instances_warning` | no heartbeat |
| Recovery | PARTIAL | `recovery` template; FAILED to ASSIGNED is allowed | no automatic recovery |
| Checkpointing | VERIFIED | handovers: `unit/test_handover.py::test_create_and_resume_cross_host` | |
| Reassignment | PARTIAL | FAILED to ASSIGNED transition (`unit/test_lifecycle.py::test_all_legal_transitions_allowed`) | manual |
| Fault isolation | VERIFIED | security flag quarantines: `unit/test_performance.py::test_security_flag_quarantines` | |

## I: Intelligence

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Decision quality | NOT BUILT | none | host's job; not measurable here |
| Context understanding | NOT BUILT | none | host's job |
| Capability matching | VERIFIED | see D: candidate selection | |
| Evidence synthesis | PARTIAL | evaluations require an `evd_` record AgentOS ran itself: `security/test_phase1_defects.py::test_d06_free_text_evidence_alone_is_rejected`, `unit/test_phase1_features.py::test_evidence_records_what_really_happened` | the host still chooses which command proves what |
| Organizational effectiveness | LATER (slice 3) | none | needs benchmarks |

## J: Job orchestration

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Task decomposition | PARTIAL | parent tasks, depth limit: `unit/test_tasks.py::test_depth_limit` | the host decomposes |
| Dependency management | VERIFIED | `unit/test_tasks.py::test_cycle_rejected`, `::test_self_dependency_rejected`, `::test_start_requires_deps_done`, `::test_cross_project_dependency_denied` | |
| Scheduling | PARTIAL | `task ready` lists startable tasks | no scheduler |
| Prioritization | VERIFIED | `unit/test_tasks.py::test_ready_orders_by_priority` | |
| Execution state | VERIFIED | `unit/test_tasks.py::test_illegal_transition`, `integration/test_cli_task.py::test_task_flow_via_cli` | |

## K: Knowledge management

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Memory quality | PARTIAL | dedupe, length limit, redaction: `unit/test_memory.py::test_dedupe`, `::test_too_long_rejected`, `::test_secret_redacted_on_write` | no quality scoring |
| Provenance | VERIFIED | source, author and confidence on every record: `integration/test_cli_flows.py::test_memory_cli_round_trip` | |
| Retrieval | VERIFIED | FTS5 search: `unit/test_memory.py::test_add_and_search`, `::test_fts_special_chars_safe`, `::test_layer_filter` | keyword search, no embeddings |
| Versioning | VERIFIED | `unit/test_memory.py::test_correct_supersedes` | |
| Knowledge transfer | VERIFIED | validated org-scope records only: `security/test_memory_isolation.py::test_org_visible_across_projects_only_when_validated` | |

## L: Learning

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Feedback capture | VERIFIED | evaluations: `unit/test_performance.py` | |
| Failure analysis | PARTIAL | `failure` memory layer, failure rate in summaries | no analysis tooling |
| Improvement hypotheses | LATER (slice 3) | none | |
| Experimentation | LATER (slice 3) | none | |
| Learning retention | PARTIAL | memory persists across sessions and hosts | no measure of reuse |

## M: Model routing

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Capability matching | LATER (slice 4) | none | templates only carry an optional `model_hint` |
| Cost-quality balance | LATER (slice 4) | none | |
| Availability checks | PARTIAL | `doctor` reports whether the Codex CLI is on PATH (`integration/test_cli_system.py::test_doctor_reports_statuses`) | |
| Fallback behavior | LATER (slice 4) | none | |
| Routing evidence | LATER (slice 4) | none | |

## N: Native integrations

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Codex compatibility | VERIFIED | Codex CLI 0.171.0, in a throwaway `CODEX_HOME`: `codex plugin marketplace add plugins/codex` then `codex plugin add agentos@agentos` gave "installed, enabled" (skill and 6 agent files in its cache) | install only; no model session was run |
| Second host (`cc`) compatibility | UNVERIFIED | `unit/test_gen.py::test_host_generate_uses_profile`; files generated locally from a git-excluded profile | not loaded by the real host yet |
| Skills compatibility | PARTIAL | `unit/test_skill_commands.py` (every command in the skill parses with the real CLI; score keys exist) | a live host following the skill is BLOCKED (see Q) |
| MCP integration | NOT BUILT | none | |
| Hooks and plugin support | PARTIAL | plugin generation verified above; hooks LATER (slice 2) | |

## O: Observability

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Logging | VERIFIED | `integration/test_cli_audit.py::test_audit_log_lists_events` | |
| Metrics | PARTIAL | `status`, `budget show`, `perf show` | no time series |
| Tracing | PARTIAL | parent/child instance links and depth | no spans |
| Auditability | VERIFIED | hash chain: `unit/test_audit.py::test_tamper_detected`, `::test_deleted_row_detected`, `integration/test_cli_audit.py::test_audit_verify_exit_5_on_tamper` | |
| Runtime visibility | PARTIAL | `agent list --active`, `status` | no dashboard (later) |

## P: Performance

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Agent quality | VERIFIED | weighted evaluation scores: `unit/test_performance.py::test_weights_sum_to_one`, `::test_weighted_renormalizes_missing_keys` | weights uncalibrated |
| Reliability | PARTIAL | failure rate and consecutive failures in summaries | |
| Latency | NOT BUILT | none | not measured |
| Resource efficiency | PARTIAL | token-estimate budgets: `unit/test_governor.py::test_budget_exceeded_and_release` | estimates only |
| Performance trends | NOT BUILT | none | |

## Q: Quality assurance

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Acceptance criteria | PARTIAL | `task add --accept` is stored | not checked automatically |
| Independent evaluation | VERIFIED | `unit/test_performance.py::test_self_eval_rejected`, `::test_parent_and_child_eval_rejected` | |
| Testing | VERIFIED | 303 tests across unit, integration, security and concurrency | |
| Regression prevention | VERIFIED | `unit/test_gen.py::test_committed_codex_plugin_is_up_to_date`, `unit/test_skill_commands.py` | no CI configured yet |
| Evidence integrity | VERIFIED | evidence required, audit chain tamper-evident (see O) | |
| Live host follows the skill | **BLOCKED** | `live/test_codex_smoke.py::test_codex_follows_skill` (written, **not run**) | uses the owner's Codex quota; runs only with `pytest -m live` after the owner's go-ahead |

## R: Reliability

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Error handling | VERIFIED | exit codes 2/3/4/5: `unit/test_cli_skeleton.py::test_agentos_error_maps_exit_code`, `integration/test_cli_template_file.py` | bad TOML and missing files no longer show tracebacks |
| Idempotency | VERIFIED | `integration/test_cli_system.py::test_init_is_idempotent`, `unit/test_db.py::test_migrate_idempotent`, `unit/test_projects.py::test_activate_twice_is_idempotent_and_audited` | |
| Circuit breakers | PARTIAL | emergency stop, retry limit | no automatic breaker |
| State consistency | VERIFIED | `unit/test_db.py::test_write_tx_rolls_back`; admission race test (see E) | |
| Failure recovery | PARTIAL | backup/restore (see AK) | |

## S: Security

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Permission boundaries | VERIFIED | `security/test_owner_guard.py` (all four tests) | |
| Isolation | VERIFIED | `security/test_memory_isolation.py`, `security/test_memory_inspect_isolation.py` | cross-project inspect leak found and fixed in this slice |
| Secret protection | VERIFIED | `security/test_redact.py`, `unit/test_audit.py::test_audit_payload_is_redacted`, `unit/test_handover.py::test_secrets_not_in_handover_file` | pattern-based; cannot catch every secret |
| Injection resistance | PARTIAL | FTS query quoting: `unit/test_memory.py::test_fts_special_chars_safe`; parameterized SQL throughout; handover path containment: `unit/test_handover.py::test_bad_id_rejected` | prompt injection into the host is out of AgentOS's reach |
| Supply-chain security | PARTIAL | one runtime dependency; `requirements-lock.txt` | no hash-pinned lock, no signing |

## T: Talent management

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Capability registry | VERIFIED | `unit/test_templates.py::test_versioning`, `::test_seed_definitions_load` | |
| Performance history | VERIFIED | `unit/test_performance.py::test_bands_and_retain` | |
| Promotion | LATER (slice 3) | none | |
| Reassignment | PARTIAL | see H | |
| Succession planning | NOT BUILT | none | |

## U: Usage optimization

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Token efficiency | NOT BUILT | none | the host's tokens are not visible to AgentOS |
| Context management | PARTIAL | handovers carry a compact summary, never transcripts | |
| Resource budgets | VERIFIED | `unit/test_governor.py::test_budget_exceeded_and_release`, `unit/test_admission.py::test_agent_run_budget` | |
| Duplicate-work prevention | VERIFIED | `unit/test_admission.py::test_duplicate`, `unit/test_memory.py::test_dedupe` | |
| Cost awareness | VERIFIED | paid spend capped at $0 by default: `unit/test_governor.py::test_paid_spend_blocked`, `::test_usd_budget_above_cap_needs_owner` | AgentOS itself makes no paid calls |

## V: Version management

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Agent versioning | VERIFIED | `unit/test_templates.py::test_versioning`, `::test_status_applies_to_all_versions` | |
| Skill versioning | PARTIAL | the skill ships inside the versioned plugin (0.1.0) | no per-skill version |
| Policy versioning | NOT BUILT | limits changes are audited, not versioned | |
| Migration | VERIFIED | `unit/test_db.py::test_migrate_idempotent`, `integration/test_cli_system.py::test_restore_rejects_newer_schema` | one migration so far |
| Rollback | PARTIAL | restore from backup (see AK) | no template rollback command |

## W: Workflow engineering

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Execution graphs | VERIFIED | task dependency DAG (see J) | |
| Parallelism | VERIFIED | see E: concurrency | |
| Communication | NOT BUILT | none | |
| Conflict resolution | NOT BUILT | none | |
| Workflow reuse | NOT BUILT | none | |

## X: Cross-platform continuity

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Handover quality | VERIFIED | `unit/test_handover.py::test_create_and_resume_cross_host`, `::test_head_advanced_and_diverged`, `::test_dirty_tree_warning` | |
| Configuration synchronization | PARTIAL | both hosts are generated from one set of definitions | the second host is UNVERIFIED (see N) |
| Shared learning | VERIFIED | one memory store for all hosts on the machine | |
| Session recovery | VERIFIED | `unit/test_handover.py::test_second_resume_denied` (single claim), `integration/test_cli_handover.py` | |
| Compatibility verification | PARTIAL | Codex plugin install verified; second host not | |

## Y: Deployment readiness

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Installation | VERIFIED | `integration/test_install_script.py::test_install_then_uninstall` (real venv, editable install, shim, init, doctor), `::test_dry_run_changes_nothing`, `::test_installer_rejects_old_python` | tested with `-NoPath`; the PATH edit itself is untested |
| Updates | PARTIAL | re-running the installer upgrades in place | no update command |
| Diagnostics | VERIFIED | `integration/test_cli_system.py::test_doctor_reports_statuses`, `integration/test_cli_audit.py::test_doctor_checks_audit_chain` | |
| Backup | VERIFIED | `integration/test_cli_system.py::test_backup_then_restore_roundtrip` | |
| Restoration | VERIFIED | same, plus `::test_restore_rejects_non_sqlite`, `::test_restore_rejects_newer_schema` | owner-only |
| Uninstallation | VERIFIED | `integration/test_install_script.py::test_install_then_uninstall`, `::test_uninstall_purge_keeps_final_backup`, `::test_uninstall_dry_run_changes_nothing` | |

## Z: Zero-fabrication integrity

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| No fabricated agents | VERIFIED | recruit reports a gap instead of inventing a template: `unit/test_recruit.py::test_gap_reported` | |
| No fabricated test results | PARTIAL | every evaluation cites at least one `evd_` record holding the real exit code and output hashes of a command AgentOS ran: `security/test_phase1_defects.py::test_d06_*`, `unit/test_performance.py::test_evidence_must_exist_and_belong_to_the_project` | a host can still run a command that proves nothing (for example `python -c "print('passed')"`); the record shows exactly what ran, so a reviewer can see it |
| No fabricated costs | VERIFIED | usage is labeled "estimates only" (handover `usage_note`); no cost is computed | |
| No fabricated performance | VERIFIED | under 5 evaluations gives `insufficient_evidence`: `unit/test_performance.py::test_insufficient_evidence_under_5`, `::test_empty_summary` | |
| No fabricated quality scores | VERIFIED | this report gives no numeric scores (see top) | |

## AA: Self-improvement effectiveness

All five (improvement over baseline, candidate validation, regression detection, reproducibility,
learning transfer): **LATER (slice 3)**. Nothing in slice 1 measures improvement.

## AB: Controlled self-evolution

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Experiment isolation | LATER (slice 3) | none | |
| Versioned proposals | PARTIAL | templates are versioned (see V) | no proposal workflow |
| Staged promotion | LATER (slice 3) | none | |
| Protected governance | VERIFIED | protected settings need the owner: `unit/test_governance.py::test_protected_setting_needs_owner` | |
| Rollback | PARTIAL | see V | |

## AC: Data management

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Database consistency | VERIFIED | `PRAGMA integrity_check` in doctor; WAL mode | |
| Transactions | VERIFIED | `unit/test_db.py::test_write_tx_rolls_back`, `::test_write_tx_commits`, `unit/test_audit.py::test_append_outside_tx_raises` | |
| Migration | VERIFIED | see V | |
| Retention | NOT BUILT | no pruning | |
| Privacy | PARTIAL | local-only storage; redaction; memory delete wipes content: `unit/test_memory.py::test_delete_wipes_content` | audit payloads are kept |

## AD: Scalability

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Queue performance | NOT BUILT | none | not benchmarked |
| Concurrency | VERIFIED | see E | |
| Load management | VERIFIED | `max_concurrent`: `unit/test_admission.py::test_max_concurrent` | |
| Resource forecasting | LATER (slice 4) | none | |
| Scaling efficiency | NOT BUILT | none | |

## AE: Maintainability

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Code quality | VERIFIED | `ruff check src tests` clean | |
| Dependency management | VERIFIED | one runtime dependency | |
| Documentation | PARTIAL | see A | |
| Testability | VERIFIED | 94% branch coverage | |
| Technical debt | PARTIAL | see `docs/LIMITATIONS.md` | |

## AF: User experience

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Installation usability | VERIFIED | dry run by default, prints every step (`integration/test_install_script.py::test_dry_run_changes_nothing`) | |
| Task visibility | VERIFIED | `task list`, `task ready`, `status` | |
| Clear error messages | VERIFIED | denial reasons listed (`unit/test_admission.py::test_all_reasons_collected`); usage errors for bad files | |
| Configuration clarity | PARTIAL | `limits show`, `budget show` | |
| Owner controls | VERIFIED | see G | |

## AG: Interoperability

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Existing framework integration | NOT BUILT | none | |
| ECC compatibility | NOT BUILT | none | |
| Portable skills | VERIFIED | one vendor-neutral skill copied to every host (`unit/test_gen.py`) | |
| Adapter architecture | VERIFIED | `gen/host.py` profiles | |
| Standard schemas | PARTIAL | JSON output on every command (`--json`) | no published schema files |

## AH: Evaluation integrity

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Benchmark protection | LATER (slice 3) | none | |
| Reviewer independence | VERIFIED | see Q | |
| Score calibration | NOT BUILT | weights are uncalibrated and labeled so | |
| Evidence traceability | VERIFIED | evidence stored with each evaluation and audited | |
| Resistance to manipulation | PARTIAL | no self or relative grading; 2 independent failing evaluators before retire review | a host can still create many evaluator ids |

## AI: Operational sustainability

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Subscription efficiency | VERIFIED | AgentOS makes no model calls | |
| Long-term maintenance | PARTIAL | small codebase, high coverage | |
| Dependency sustainability | VERIFIED | stdlib plus pydantic | |
| Operational overhead | VERIFIED | no service to run | |
| Incremental extensibility | VERIFIED | see A | |

## AJ: Compliance and external actions

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Provider usage restrictions | VERIFIED | no provider APIs called; hosts run under their own terms | |
| Authorization | VERIFIED | see G | |
| Data handling | PARTIAL | see AC: privacy | |
| External action boundaries | VERIFIED | AgentOS does no network I/O; the installer never edits the Codex config | |
| License compliance | VERIFIED | MIT `LICENSE`; pydantic is MIT | |

## AK: Disaster recovery

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Backups | VERIFIED | see Y | |
| Restoration | VERIFIED | see Y; restore keeps a safety copy of the replaced DB | |
| Interrupted tasks | VERIFIED | handovers and orphan warnings (see H, X) | |
| Recovery testing | VERIFIED | `integration/test_cli_system.py::test_backup_then_restore_roundtrip` | |
| Recovery documentation | PARTIAL | README quickstart | no runbook |

## AL: Developer experience

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| CLI usability | VERIFIED | `--help` on every command; `unit/test_skill_commands.py` | |
| Configuration validation | VERIFIED | `unit/test_governor.py::test_unknown_limit_rejected`, `integration/test_cli_template_file.py::test_template_add_invalid_schema`, `unit/test_gen.py::test_host_profile_missing_key` | |
| Examples | PARTIAL | README quickstart, skill | |
| Debugging | PARTIAL | `audit log`, `agent inspect` | |
| Troubleshooting | PARTIAL | `doctor` | |

## AM: Strategic decision quality

All five (alternative comparison, uncertainty handling, risk analysis, cost-benefit evaluation,
decision traceability): the host's job. **NOT BUILT** in AgentOS, except decision traceability,
which is **PARTIAL**: decisions can be stored in the `project` and `governance` memory layers and
are carried in handovers (`unit/test_handover.py::test_create_and_resume_cross_host`).

## AN: Multi-project operation

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Project activation | VERIFIED | `unit/test_projects.py` (all), `integration/test_cli_flows.py::test_project_list_and_deactivate` | |
| Memory isolation | VERIFIED | see S | |
| Project budgets | VERIFIED | project-scope budgets: `unit/test_governor.py::test_budget_exceeded_and_release`, `unit/test_admission.py::test_agent_run_budget` | |
| Cross-project coordination | PARTIAL | cross-project dependencies are refused (`unit/test_tasks.py::test_cross_project_dependency_denied`) | no coordination feature |
| Project-specific governance | PARTIAL | inactive projects are refused (`unit/test_projects.py::test_require_active_denies_inactive`) | limits are global and per host, not per project |

## AO: Supply-chain and release integrity

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Dependency provenance | PARTIAL | PyPI only | no hash checking |
| Version pinning | PARTIAL | `requirements-lock.txt` | `pip install -e` resolves from `pyproject.toml` ranges |
| Release reproducibility | NOT BUILT | no release build | |
| Update safety | PARTIAL | generators never overwrite hand-edited files: `unit/test_gen.py::test_generator_preserves_human_edits` | |
| Rollback verification | PARTIAL | backup/restore round trip | no release rollback |

---

## Found and fixed during this slice

Each was found by a test or a live run. Each fix went test-first (RED, then GREEN).

- Windows `NUL` reports `isatty()` as true, so the owner prompt was reachable without a console. The owner check now also asks the console API. (`security/test_owner_guard.py`)
- `approval deny` wrote an "approval.denied" audit event for approvals that were already granted or consumed, while leaving them usable. It now refuses anything not pending, inside the transaction. (`unit/test_governance_edges.py::test_deny_granted_approval_is_refused_and_not_audited`)
- `memory inspect` read any project's records by id. It now refuses other projects' records except shared ones. (`security/test_memory_inspect_isolation.py`)
- The skill told hosts to use score keys that don't exist, so every evaluation would have failed. (`unit/test_skill_commands.py::test_skill_score_keys_are_real`)
- TOML files with a UTF-8 BOM (written by Notepad and Windows PowerShell 5.1) crashed with a traceback. (`unit/test_gen.py::test_host_profile_with_bom_is_accepted`)

---

## V4.0 Phase 1: suspected-defect register

The V4.0 recovery brief listed 17 suspected defects. Each one was reproduced with a test that
asserts the correct behaviour (`security/test_phase1_defects.py`) and run against the unfixed code
(commit `1b7d492`) before anything changed. **Confirmed** means that test failed for the stated
reason on the unfixed code. D05 and D07 were first run with a test helper that didn't exist yet,
so they were re-confirmed with a standalone script against the unfixed code: a made-up evaluator,
an evaluator from another project, a second grade from the same evaluator and a `speed=100`-only
grade (weighted 100.0) were all accepted. All fixes went test-first; the same tests pass now.

| # | Suspected defect | Before fix | Fix | Evidence now |
| --- | --- | --- | --- | --- |
| D01 | Cooperative-only admission | **Confirmed, architectural**: nothing stops a host that never calls `agent admit` | not fixable in the ledger; needs host hooks (Phase 2) | LIMITATIONS.md |
| D02 | Missing runtime cancellation | **Confirmed, architectural**: AgentOS has no handle on a host's worker process | slot now held until the host confirms the stop (D03); real cancellation needs runtime adapters (Phase 2) | LIMITATIONS.md |
| D03 | Premature release of active-worker slots | **Confirmed**: CANCELLED, and TERMINATED without confirmation, freed the slot at once | `lifecycle.slot_count` counts them until `agent confirm-stop` or `TERMINATED --confirmed`; archiving them needs confirmation | `test_d03_*`, `unit/test_phase1_features.py::test_confirm_stopped_paths` |
| D04 | Lifecycle transitions bypassing admission | **Confirmed**: FAILED to ASSIGNED ignored `max_concurrent` and the emergency stop | entering an active state runs admission's `standing_reasons` and reserves another agent run | `test_d04_*`, `::test_reentry_reserves_a_run_and_respects_budget` |
| D05 | Unauthenticated evaluator identities | **Confirmed**: any string, and instances of other projects, were accepted | evaluator must be a registered instance of the same project, or `owner` with owner confirmation | `test_d05_*`, `unit/test_performance.py::test_owner_may_grade_only_with_confirmation` |
| D06 | Fabricated or unverifiable evidence | **Confirmed**: free text such as "999 passed (trust me)" was accepted | `agentos evidence run` executes the command and records exit code, output hashes, redacted tail and Git HEAD; a grade needs one such `evd_` record of the same project, newer than the graded agent | `test_d06_*`, `::test_evidence_*` |
| D07 | Duplicate or selectively incomplete evaluations | **Confirmed**: repeat grades and partial score sets were accepted | one grade per (agent, evaluator, category), checked inside the write transaction; all 8 scores required | `test_d07_*`, `unit/test_performance.py::test_every_score_is_required` |
| D08 | Cross-project parent delegation | **Confirmed** | `parent_cross_project` | `test_d08_*` |
| D09 | Missing dependency checks in admission | **Confirmed** | `dependencies_incomplete` | `test_d09_*` |
| D10 | Missing capability and risk validation | **Confirmed** | `capability_mismatch`; `high` risk needs 3+ evaluations averaging 85+ or a one-use owner approval; `critical` always needs the approval | `test_d10_*`, `::test_high_risk_*`, `::test_critical_risk_*`, `::test_denied_admission_does_not_consume_the_approval` |
| D11 | Race in task dependency creation | **Confirmed**: a forced interleaving created A->B and B->A | cycle check and insert share one `BEGIN IMMEDIATE` transaction | `test_d11_*` |
| D12 | Insufficient reservation validation | **Confirmed**: negative and zero amounts were stored (a negative one refunded a budget); NaN crashed with a raw SQLite error | kind, scope and amount (finite, above 0) validated; `budget set` validated too | `test_d12_*`, `::test_set_budget_validation` |
| D13 | Budget enforcement gaps | **Confirmed**: nothing ever charged `tokens_est` or `usd`, so those budgets could not be exceeded | `budget use` charges before spending (exit 3 if over); admission refuses once a token or paid budget is used up | `test_d13_*`, `::test_usage_validation_and_usd_cap`, `::test_budget_use_cli` |
| D14 | Audit-chain truncation | **Confirmed**: deleting the newest events left `audit verify` passing | verify checks sequence gaps and the AUTOINCREMENT counter; `audit anchor` / `verify --anchor` catches a rewrite of the whole chain | `test_d14_*`, `::test_anchor_*`, `::test_truncation_reason_reported` |
| D15 | Weak owner identity | **Confirmed**: the typed phrase, which the prompt itself prints, was the only factor | optional owner PIN (scrypt, asked unechoed, never logged) on every owner confirmation | `test_d15_*`, `::test_owner_pin_cli`, `::test_pin_must_be_long_enough_and_needs_owner` |
| D16 | Secret-redaction limits | **Confirmed** for 9 formats: JWT, Bearer, Google, Stripe live/restricted, URL passwords, JSON `"password":`, `client_secret=`, `AWS_SECRET_ACCESS_KEY=` | patterns added; ordinary words such as `tokens_est` and `secretary` stay untouched | `test_d16_*`, `::test_redaction_leaves_ordinary_text` |
| D17 | Incomplete project isolation | **Confirmed**: `agent transition / inspect` and `task start / inspect` acted on another project's records | commands acting on one record by id check it belongs to the current project (`cross_project`, exit 3); also `task dep`, `eval record`, `budget use`, `evidence show` | `test_d17_*` |

### What these fixes do not change

- An agent that can write the SQLite file directly can still do anything; the chain is unkeyed,
  so only an anchor kept outside the agent's reach proves the whole history (D14).
- Evaluator identity is bound to a registered instance, not authenticated: a host that knows
  another instance's id can still pass it (D05). Real authentication needs per-agent credentials
  issued by the host runtime (Phase 2).
- D01 and D02 stay open until runtime adapters exist.
