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

Evidence paths are relative to `tests/`. Test run at time of writing (after V4.0 Phase 6,
host integration): `python -m pytest -q` gives **621 passed** (the live test is excluded by
default). Branch coverage is 95% overall: adapters 93%, host CLI 100%, improve 98%, policy 100%, improve CLI 96%, recruit 93%, templates 95%, factory 93%, workforce 97%, boss 92%, runtime 93%, hook CLI 100%, admission 96%, audit 97%, evidence 95%, governance 97%, governor 96%, lifecycle 97%, performance 95%, redact 100%. After Phase 5 it was 596 passed, after Phase 4 537, after Phase 3 467, after Phase 2 425, after Phase 1 381. `ruff check src tests` is clean. A fresh clone of the pre-fix commit `1b7d492` gave
303 passed and a clean ruff run, which is the Phase 0 baseline.

### Host role

AgentOS is the ledger and referee. The host session (Codex, or the second host `cc`) plans,
writes code and decides. Rows about the host's thinking (B, I, M, AM) are therefore mostly
about what AgentOS *records and enforces*, not about decision quality, which slice 1 cannot measure.

---

## A: Architecture

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Modularity | VERIFIED | one module per concern under `src/agentos/`; each has its own unit test file | 26 core modules, a 4-file generator package, 19 CLI command modules |
| Extensibility | PARTIAL | `cli/__init__.py` `COMMAND_MODULES`; `gen/host.py` profiles (`unit/test_gen.py::test_host_generate_uses_profile`) | adding a command or host needs no core change; no plugin API for third parties |
| Separation of concerns | VERIFIED | CLI handlers call core functions only; core never imports `cli` | the owner prompt lives in `governance` |
| Dependency boundaries | VERIFIED | `pyproject.toml`: one runtime dependency (pydantic) | stdlib for SQLite, TOML, argparse |
| Architectural simplicity | VERIFIED | no daemon, no network, no model calls; one SQLite file | |
| Configuration design | PARTIAL | limits and budgets in the DB (`unit/test_governor.py`); host profiles in TOML | no config file for the CLI itself |
| Documentation | PARTIAL | `README.md`, `docs/HOST_PROFILE.md`, `docs/LIMITATIONS.md`, design spec and plan | no API reference |

## B: Boss agent

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Objective understanding | PARTIAL | objectives need testable acceptance criteria: `unit/test_boss.py::test_objective_needs_acceptance_criteria`; complexity recorded: `::test_objective_records_complexity` | the host understands the objective; AgentOS records it and refuses a vague one |
| Planning | PARTIAL | `plan score`: `unit/test_complexity.py`; plans applied atomically with validation: `unit/test_boss.py::test_plan_is_all_or_nothing`, `::test_plan_validation`, `::test_plan_creates_linked_tasks_and_dependencies` | decomposition quality is the host's; heuristics uncalibrated |
| Decision-making | PARTIAL | scheduling by critical path and capacity: `unit/test_boss.py::test_schedule_puts_the_critical_path_first`, `::test_schedule_respects_capacity` | advisory; the host decides and admission gates |
| Delegation | VERIFIED | `unit/test_admission.py::test_depth_and_delegation`, `::test_parent_must_be_active` | only `can_delegate` templates may spawn children |
| Coordination | PARTIAL | task dependencies and `task ready`: `unit/test_tasks.py::test_ready_orders_by_priority` | no messaging between agents |
| Accountability | VERIFIED | every state change is audited: `unit/test_lifecycle.py::test_illegal_transition_audited`, `unit/test_admission.py::test_denial_is_audited` | |
| Escalation | PARTIAL | owner-only actions refuse without the owner: `security/test_owner_guard.py`; `boss recover` escalates to the owner once retries are spent: `unit/test_boss.py::test_recover_escalates_when_retries_run_out` | the owner is told through the host, not notified directly |

## C: Corporate hierarchy

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Clear authority | VERIFIED | owner vs host split: `unit/test_governance.py::test_cannot_forge_confirmation`, `security/test_owner_guard.py::test_no_env_var_bypass` | |
| Role separation | VERIFIED | read-only reviewer and researcher templates; no self-grading: `unit/test_performance.py::test_self_eval_rejected`, `::test_parent_and_child_eval_rejected` | |
| Dynamic departments | VERIFIED | dissolution: `unit/test_workforce.py::test_contract_archives_dissolves_and_expires`, `::test_dissolved_department_can_form_again`; creation: `unit/test_boss.py::test_departments_only_when_the_work_justifies_one`, `::test_large_objectives_may_get_a_department_lead`, `::test_no_executive_worker_for_routine_work` | departments are ledger records; a lead worker is only suggested |
| Managerial effectiveness | NOT BUILT | none | not measurable in slice 1 |
| Organizational adaptability | PARTIAL | templates and recruitment weights change through validated experiments: `unit/test_improve.py::test_a_better_challenger_is_promoted_into_the_champion`, `::test_a_better_policy_is_promoted_then_monitored` | not measured across real objectives |

## D: Dynamic recruitment

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Capability detection | VERIFIED | `unit/test_recruit.py::test_gap_reported`; `integration/test_cli_flows.py::test_eval_perf_and_recruit` | reports missing capabilities, never invents a template |
| Candidate selection | VERIFIED | `unit/test_recruit.py::test_rank_prefers_match`, `::test_rank_prefers_history_on_equal_match`, `::test_high_risk_requires_proven` | weights uncalibrated |
| Onboarding | VERIFIED | `template add` / `seed`: `unit/test_templates.py::test_seed_definitions_load`; factory registration: `unit/test_factory.py::test_register_adds_an_active_template`; a new template has no record, so high-risk work refuses it | probation exists for rehabilitated templates, not for brand-new ones |
| Validation | PARTIAL | schema plus safety validation of factory configs: `unit/test_factory.py::test_unsafe_configurations_are_refused`, `::test_safety_rules_are_always_appended`, `::test_wider_permissions_wait_for_the_owner` | no behavioural test of a new template before use |
| Recruitment efficiency | PARTIAL | `factory recruit` reuses a covering template and reuses an open proposal: `unit/test_factory.py::test_recruit_uses_an_existing_template_when_one_fits`, `::test_recruit_waits_for_the_owner_on_a_pending_proposal` | not measured |

## E: Elastic workforce scaling

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Recursive delegation | VERIFIED | `unit/test_admission.py::test_depth_and_delegation` | depth capped by `max_depth` (default 2) |
| Concurrency | VERIFIED | `concurrency/test_parallel_admission.py::test_parallel_processes_never_exceed_limit` | 12 processes race; exactly 4 admitted |
| Workload adaptation | VERIFIED | `workforce split` by effort and free slots: `unit/test_workforce.py::test_split_by_workload`, `::test_split_respects_free_slots`, `::test_split_refuses_more_workers_than_work` | each part still needs admission |
| Overhead management | PARTIAL | `max_agents_per_task`: `unit/test_admission.py::test_max_agents_per_task` | |
| Workforce contraction | VERIFIED | slots free on leaving active states: `unit/test_admission.py::test_release_on_completion`; `workforce contract`: `unit/test_workforce.py::test_contract_archives_dissolves_and_expires` | running workers are reported, not stopped |

## F: Firing and replacement

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Performance diagnosis | VERIFIED | `unit/test_performance.py::test_bands_and_retain`, `::test_critical_visible_despite_high_mean`, `::test_external_cause_excluded` | |
| Rehabilitation | VERIFIED | new version on probation: `unit/test_workforce.py::test_rehabilitation_passes_on_probation`, `::test_failed_rehabilitation_suspends`, `::test_rehabilitation_cannot_widen_permissions` | the improvement itself is written by the host |
| Suspension | VERIFIED | `unit/test_templates.py::test_suspend_and_reinstate_without_owner`; performance-based: `unit/test_workforce.py::test_review_suspends_after_failing_in_a_row`, `::test_review_suspends_on_retire_review_but_leaves_retirement_to_the_owner` | |
| Safe cancellation | PARTIAL | CANCELLED then TERMINATED, recorded as unconfirmed: `unit/test_lifecycle.py::test_terminate_unconfirmed_is_recorded`; `workforce terminate`: `unit/test_workforce.py::test_terminate_active_worker_keeps_its_slot_until_the_stop_is_confirmed` | AgentOS cannot stop a host's native worker; see LIMITATIONS |
| Replacement | VERIFIED | `workforce transfer` picks the best other covering template and checks admission before stopping the old worker: `unit/test_workforce.py::test_transfer_picks_a_replacement_and_briefs_it`, `::test_refused_transfer_leaves_the_old_worker_running`; retire needs the owner | the host must stop the old native worker |
| Knowledge preservation | VERIFIED | termination and transfer notes go to project memory, failures to the failure layer: `unit/test_workforce.py::test_terminate_failed_worker_records_a_failure_lesson`; evaluations and evidence carried in the transfer briefing | the note is what the host writes |

## G: Governance

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Owner authority | VERIFIED | `unit/test_governance.py::test_cannot_forge_confirmation`, `unit/test_governor.py::test_raise_limit_needs_owner`, `unit/test_templates.py::test_retire_requires_owner`, `integration/test_cli_system.py::test_restore_without_owner_denied` | owner types `I APPROVE <action>` at a real console |
| Approval requirements | VERIFIED | `unit/test_governance.py::test_approval_bound_to_params`, `::test_approval_single_use`, `::test_approval_expires`; `unit/test_governance_edges.py::test_deny_granted_approval_is_refused_and_not_audited` | |
| Policy enforcement | PARTIAL | admission refuses with every reason: `unit/test_admission.py::test_all_reasons_collected`; with the Codex hooks trusted, the spawn itself is refused without an admitted instance: `unit/test_runtime.py::test_spawn_without_a_ticket_is_denied`, `::test_emergency_stop_denies_spawn_even_with_a_ticket`, `integration/test_cli_hook.py` | hooks work only once the owner trusts them; no live spawn through the hook yet (needs quota); hosts without hooks still rely on asking |
| Emergency controls | VERIFIED | `unit/test_governance.py::test_stop_blocks_admission_but_allows_winddown`, `integration/test_cli_flows.py::test_emergency_stop_blocks_admission_and_lift_needs_owner` | |
| Independent oversight | VERIFIED | evaluator independence: `unit/test_performance.py::test_parent_and_child_eval_rejected` | |

## H: Self-healing

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Failure detection | PARTIAL | FAILED state, retry limit: `unit/test_tasks.py::test_retry_limit`; orphan warnings on resume: `unit/test_handover.py::test_orphaned_instances_warning` | no heartbeat |
| Recovery | PARTIAL | `boss recover` retries with a template that has not failed the task: `unit/test_boss.py::test_recover_retries_with_another_template` | the host must start the retry |
| Checkpointing | VERIFIED | handovers: `unit/test_handover.py::test_create_and_resume_cross_host` | |
| Reassignment | VERIFIED | `workforce transfer`: `unit/test_workforce.py::test_transfer_picks_a_replacement_and_briefs_it`, `::test_transfer_to_a_named_template`, `integration/test_cli_workforce.py::test_split_then_terminate_and_transfer` | |
| Fault isolation | VERIFIED | security flag quarantines: `unit/test_performance.py::test_security_flag_quarantines` | |

## I: Intelligence

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Decision quality | NOT BUILT | none | host's job; not measurable here |
| Context understanding | NOT BUILT | none | host's job |
| Capability matching | VERIFIED | see D: candidate selection | |
| Evidence synthesis | PARTIAL | evaluations require an `evd_` record AgentOS ran itself: `security/test_phase1_defects.py::test_d06_free_text_evidence_alone_is_rejected`, `unit/test_phase1_features.py::test_evidence_records_what_really_happened` | the host still chooses which command proves what |
| Organizational effectiveness | UNVERIFIED | benchmark cases now exist (`improve case`), but no real-outcome benchmark has been run | needs real objectives graded over time |

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
| Failure analysis | VERIFIED | `improve retro` diagnoses weak sub-scores, failing evidence and recurring refusals: `unit/test_improve.py::test_retro_diagnoses_weaknesses_and_proposes_a_testable_change`, `::test_recurring_capability_mismatches_suggest_a_recruitment_policy` | thresholds hand-picked |
| Improvement hypotheses | VERIFIED (rule-based) | same tests; a tried change or a busy target is not proposed again | fixed addenda, not model-written |
| Experimentation | VERIFIED | champion versus challenger: see "V4.0 Phase 5" | small case counts |
| Learning retention | PARTIAL | memory persists across sessions and hosts; promotions write validated org memory: `::test_a_better_challenger_is_promoted_into_the_champion` | no measure of reuse |

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
| Second host (`cc`) compatibility | VERIFIED (validate) | `agentos host install cc` from a git-excluded profile; the host's own `plugin validate` (version 2.1.181) passed with no warnings on the installed folder; live spawn gate below | the installed plugin was validated, not loaded into a live session |
| Skills compatibility | PARTIAL | `unit/test_skill_commands.py` (every command in the skill parses with the real CLI; score keys exist) | a live host following the skill is BLOCKED (see Q) |
| MCP integration | NOT BUILT | none | |
| Hooks and plugin support | PARTIAL | the plugin ships `hooks/hooks.json`; the real Codex CLI 0.171.0 discovers all three hooks with no errors, untrusted until the owner trusts them: `integration/test_codex_hook_discovery.py` (app-server `hooks/list`, no model call); handler: `unit/test_runtime.py` | a live spawn through the Codex hook is not run yet (no quota); the `cc` host ran it live (see Phase 2) |

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
| Testing | VERIFIED | 537 tests across unit, integration, security and concurrency | |
| Regression prevention | VERIFIED | `unit/test_gen.py::test_committed_codex_plugin_is_up_to_date`, `unit/test_skill_commands.py`; CI in `.github/workflows/ci.yml` (lint and tests, Windows and Ubuntu, Python 3.11 and 3.12) | first run (45842647948) failed on Ubuntu only: a test assumed case-insensitive paths; fixed in `b8a2a74`, then run 45843512290 passed on all four jobs. The Codex discovery test skips on CI, which has no Codex CLI |
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
| Promotion | VERIFIED | a challenger becomes a new champion version only through `improve decide`: `unit/test_improve.py::test_a_better_challenger_is_promoted_into_the_champion`, `::test_a_weaker_challenger_is_rejected_and_remembered` | |
| Reassignment | PARTIAL | see H | |
| Succession planning | VERIFIED | `unit/test_workforce.py::test_succession_finds_successors_and_single_points_of_failure` | |

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
| Rollback | VERIFIED | restore from backup (see AK); plugin updates: `unit/test_adapters.py::test_update_backs_up_and_rollback_restores_exactly`; promoted changes: `unit/test_improve.py` (monitor rollback) | no release rollback (see AK) |

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
| Configuration synchronization | VERIFIED | both hosts from one set of definitions; `host drift` finds stale installs: `unit/test_adapters.py::test_drift_finds_hand_edits_deletions_stale_definitions_and_host_updates` | |
| Shared learning | VERIFIED | one memory store for all hosts on the machine | |
| Session recovery | VERIFIED | `unit/test_handover.py::test_second_resume_denied` (single claim), `integration/test_cli_handover.py` | |
| Compatibility verification | PARTIAL | Codex plugin accepted by Codex 0.171.0; second host plugin validated by the host; cross-host work both ways through the CLI: `integration/test_cli_host.py::test_work_and_learning_cross_hosts_both_ways` | live Codex session BLOCKED (no quota) |

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

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Improvement over baseline | VERIFIED (mechanism) | promotion needs a representative gain of 2 points with more wins than losses and no held-out loss: `unit/test_improve.py::test_a_better_challenger_is_promoted_into_the_champion`, `::test_a_weaker_challenger_is_rejected_and_remembered` | no real improvement has been measured yet; that needs real work graded over time |
| Candidate validation | VERIFIED | isolated candidate, safety re-check, gate: `::test_the_challenger_is_an_isolated_candidate`, `::test_a_failing_gate_blocks_promotion`, `::test_unsafe_or_identical_challengers_are_refused` | |
| Regression detection | VERIFIED | `::test_a_regression_after_promotion_is_rolled_back`, `::test_a_holding_improvement_is_adopted` | 5-grade window, 5-point margin: uncalibrated |
| Reproducibility | PARTIAL | cases are content-hashed, fixed before the experiment and run by AgentOS; every step is audited | host workers are not deterministic |
| Learning transfer | PARTIAL | promotions write validated organization-wide memory | reuse is not measured |

## AB: Controlled self-evolution

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Experiment isolation | VERIFIED | a `candidate` template is never recruited and is admitted only on its own running experiment's trials: `unit/test_improve.py::test_the_challenger_is_an_isolated_candidate` | |
| Versioned proposals | VERIFIED | experiments record champion version and challenger; promotion adds a version, rollback re-adds the previous one: `::test_a_regression_after_promotion_is_rolled_back` | |
| Staged promotion | VERIFIED | trialing, then promoted, then adopted or rolled back: `::test_a_holding_improvement_is_adopted` | |
| No unauthorized self-modification | VERIFIED | only instructions, description and hints, and bounded recruitment weights, are tunable: `::test_experiments_cannot_touch_permissions_or_security`, `unit/test_policy.py::test_sensitive_or_unknown_names_are_not_tunable`; hand replacement needs the owner: `integration/test_cli_improve.py::test_replacing_a_working_template_needs_the_owner` | |
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
| Testability | VERIFIED | 95% branch coverage | |
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
| ECC compatibility | VERIFIED (static) | `agentos host check cc` against the installed ECC plugin: compatible (its PreToolUse hooks run alongside; same-named agents are namespaced; no duplicate AgentOS hooks); `unit/test_adapters.py::test_check_*` | not exercised in a live session with both loaded |
| Portable skills | VERIFIED | one vendor-neutral skill copied to every host (`unit/test_gen.py`) | |
| Adapter architecture | VERIFIED | `gen/host.py` profiles | |
| Standard schemas | PARTIAL | JSON output on every command (`--json`) | no published schema files |

## AH: Evaluation integrity

| Criterion | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Benchmark protection | VERIFIED | held-out cases hidden, leakage refused, late cases excluded, used held-out cases demoted: `unit/test_improve.py::test_held_out_cases_are_hidden_from_listings_and_the_audit`, `::test_a_challenger_that_copies_a_held_out_case_is_refused`, `::test_cases_added_after_the_experiment_do_not_count`, `::test_used_held_out_cases_no_longer_count_as_held_out` | leakage check is textual |
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
| D01 | Cooperative-only admission | **Confirmed, architectural**: nothing stops a host that never calls `agent admit` | **Phase 2, partly fixed**: Codex `PreToolUse` hook on `spawn_agent` refuses a spawn with no admitted ticket; `SubagentStart` binds the native agent and records unadmitted ones | `unit/test_runtime.py`, `integration/test_cli_hook.py`, `integration/test_codex_hook_discovery.py`; open: owner must trust the hooks, no live spawn run yet |
| D02 | Missing runtime cancellation | **Confirmed, architectural**: AgentOS has no handle on a host's worker process | **Phase 2, partly fixed**: `SubagentStop` confirms a requested cancel (frees the slot); with `--guard-tools` a cancelled worker's tool calls are refused | `unit/test_runtime.py::test_subagent_stop_confirms_a_requested_cancel`, `::test_tool_calls_of_a_cancelled_subagent_are_denied`; open: AgentOS still cannot kill a subagent, and whether Codex sends `agent_id` on tool calls is unverified |
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
- D01 and D02 are partly closed by the Phase 2 runtime hooks (below).

---

## V4.0 Phase 2: runtime hooks

Researched before building, not assumed: Codex CLI 0.171.0 reports the `hooks` feature as
stable and enabled (`codex features list`); the binary contains the events `PreToolUse`,
`SubagentStart`, `SubagentStop` and the fields `permissionDecision`, `agent_id`, `agent_type`;
the published hooks documentation says `PreToolUse` can deny a tool call (including the
`spawn_agent` tool) and `SubagentStart` cannot block.

| What | Status | Evidence | Open |
| --- | --- | --- | --- |
| Spawn gate (`PreToolUse` on `spawn_agent`/`Agent`) | VERIFIED in tests | `unit/test_runtime.py::test_spawn_without_a_ticket_is_denied`, `::test_spawn_with_a_ticket_is_allowed_once`, `::test_named_ticket_is_claimed_and_unavailable_names_are_denied`, `::test_ticket_from_another_project_cannot_be_named`, `::test_the_same_spawn_call_checked_twice_claims_one_ticket` | live spawn not run |
| Fail closed | VERIFIED in tests | `integration/test_cli_hook.py::test_hook_failure_refuses_spawn_but_not_other_tools` | |
| Binding and RUNNING on start | VERIFIED in tests | `unit/test_runtime.py::test_subagent_start_binds_and_starts_running`, `::test_unadmitted_subagent_is_recorded_and_told` | seen live on `cc`: a subagent reports its parent's `session_id`, which the binder prefers; Codex unverified |
| Stop confirmation | VERIFIED in tests | `::test_subagent_stop_confirms_a_requested_cancel`, `::test_subagent_stop_of_running_work_only_records_it` | |
| Cancelled worker's tool calls refused (`--guard-tools`) | PARTIAL | `::test_tool_calls_of_a_cancelled_subagent_are_denied`, `::test_emergency_stop_denies_tool_calls_of_bound_subagents` | needs `agent_id` on a subagent's tool calls: seen live on `cc` (`::test_main_thread_calls_without_agent_id_pass_guard_mode` mirrors it); Codex unverified |
| Real process, UTF-8 stdin, non-ASCII path | VERIFIED | `integration/test_cli_hook.py::test_real_process_with_a_non_ascii_path` | |
| Codex loads the plugin hooks | VERIFIED | `integration/test_codex_hook_discovery.py` (real CLI, throwaway `CODEX_HOME`, no model call) | they stay untrusted until the owner trusts them in `/hooks` |
| Second host (`cc`) spawn gate | VERIFIED (live) | live on 2026-11-26 with version 2.1.331, in a throwaway AgentOS home: a spawn with no admitted instance was refused with AgentOS's reason; a spawn naming an admitted instance was allowed, bound to the runtime's agent id and moved to RUNNING, and its stop was recorded; `audit verify` passed; repeated SubagentStop seen live, now `::test_repeated_subagent_stop_is_idempotent` | the generated plugin itself was not installed in that host; the hooks were loaded from a local settings file |

## V4.0 Phase 3: Boss loop

Built as ledger checks the host calls (`agentos boss`), not as a new model-calling agent. See
[docs/BOSS.md](../docs/BOSS.md).

| Responsibility | Status | Evidence | Open |
| --- | --- | --- | --- |
| Objective understanding | VERIFIED (record and refuse) | `unit/test_boss.py::test_objective_needs_acceptance_criteria` | the understanding itself is the host's |
| Complexity assessment | VERIFIED | `::test_objective_records_complexity`, `integration/test_cli_boss.py::test_boss_start_input_checks` | weights uncalibrated |
| Dynamic decomposition | VERIFIED (validation) | `::test_plan_is_all_or_nothing`, `::test_plan_validation`, `::test_replan_can_build_on_existing_tasks_of_the_objective` | plan quality is the host's |
| Dependency-aware scheduling | VERIFIED | `::test_schedule_puts_the_critical_path_first`, `::test_schedule_respects_capacity` | advisory |
| Department creation | VERIFIED | `::test_departments_only_when_the_work_justifies_one` | thresholds hand-picked |
| Specialist recruitment | VERIFIED | `::test_schedule_flags_tasks_no_template_can_do`, `::test_plan_reports_capability_gaps` | |
| Recursive workforce expansion | VERIFIED | `::test_large_objectives_may_get_a_department_lead`; depth still capped by admission | suggestion only |
| Resource allocation | VERIFIED | `::test_schedule_respects_capacity` | |
| Bottleneck detection | VERIFIED | `::test_bottlenecks`, `::test_orphan_worker_is_a_bottleneck` | stale threshold uncalibrated |
| Independent quality control | VERIFIED | `::test_accept_needs_independent_passing_evidence` | evaluator identity still unauthenticated (see LIMITATIONS) |
| Failure recovery | VERIFIED | `::test_recover_retries_with_another_template`, `::test_recover_escalates_when_retries_run_out`, `::test_recover_only_failed_tasks` | |
| Final delivery | VERIFIED | `::test_delivery_is_gated`, `::test_cancelled_tasks_do_not_block_delivery`, `::test_plans_cannot_change_a_delivered_objective` | |
| Nine executive functions | VERIFIED (as checks) | `::test_review_covers_every_executive_function` | checks, not workers, by design |
| No executive workers for routine work | VERIFIED | `::test_no_executive_worker_for_routine_work`, `integration/test_cli_boss.py::test_boss_loop_end_to_end` | |
| CLI end to end | VERIFIED | `integration/test_cli_boss.py::test_boss_loop_end_to_end` (start, plan, next, admit, evidence, grade, accept, deliver, show, `audit verify`) | not run in a live host session |

## V4.0 Phase 4: Agent Factory and workforce management

See [docs/WORKFORCE.md](../docs/WORKFORCE.md). Everything runs on the ledger and through
admission; nothing starts or kills a native worker.

| Requirement | Status | Evidence | Open |
| --- | --- | --- | --- |
| Gap to specialist: propose, validate, register, recruit | VERIFIED | `unit/test_factory.py::test_gap_becomes_a_safe_proposal`, `::test_register_adds_an_active_template`, `::test_recruit_builds_and_admits_a_specialist_for_a_gap`, `integration/test_cli_workforce.py::test_factory_fills_a_gap_and_recruits` | drafts are rule-based; quality shows only in later evaluations |
| Within approved permissions | VERIFIED | `::test_wider_permissions_wait_for_the_owner`, `::test_draft_inherits_from_the_closest_template`, `integration/test_cli_workforce.py::test_wider_specialist_needs_the_owner` | |
| Within approved budgets and limits | VERIFIED | `::test_factory_limit_caps_live_specialists`, `::test_recruit_still_goes_through_admission` | |
| Unsafe configurations refused | VERIFIED | `::test_unsafe_configurations_are_refused`, `::test_safety_rules_are_always_appended`, `::test_unknown_override_fields_are_refused` | phrase list is fixed, not semantic |
| Performance-based candidate selection | VERIFIED | `unit/test_recruit.py::test_rank_prefers_history_on_equal_match`; used by `factory recruit` and `workforce transfer` | weights uncalibrated |
| Dynamic recruitment | VERIFIED | `unit/test_factory.py::test_recruit_uses_an_existing_template_when_one_fits`, `::test_recruit_builds_and_admits_a_specialist_for_a_gap` | |
| Temporary specialist configurations | VERIFIED | `::test_temporary_specialists_expire_unless_busy`, `::test_busy_specialist_is_kept_past_expiry`, `::test_permanent_specialists_never_expire` | |
| Department creation and dissolution | VERIFIED | `unit/test_boss.py::test_departments_only_when_the_work_justifies_one`, `unit/test_workforce.py::test_contract_archives_dissolves_and_expires`, `::test_dissolved_department_can_form_again` | |
| Workload-based subagent multiplication | VERIFIED | `unit/test_workforce.py::test_split_by_workload`, `::test_split_respects_free_slots`, `::test_split_refuses_more_workers_than_work` | |
| Recursive delegation | VERIFIED | `unit/test_admission.py::test_depth_and_delegation` (unchanged); factory specialists cannot delegate without the owner | |
| Workforce contraction | VERIFIED | `unit/test_workforce.py::test_contract_archives_dissolves_and_expires` | running workers are reported, not stopped |
| Succession planning | VERIFIED | `::test_succession_finds_successors_and_single_points_of_failure` | |
| Agent rehabilitation | VERIFIED | `::test_rehabilitation_passes_on_probation`, `::test_failed_rehabilitation_suspends`, `::test_rehabilitation_reinstates_a_suspended_template_on_probation`, `::test_rehabilitation_cannot_widen_permissions` | |
| Performance-based suspension | VERIFIED | `::test_review_suspends_after_failing_in_a_row`, `::test_review_suspends_on_retire_review_but_leaves_retirement_to_the_owner`, `::test_review_leaves_good_templates_alone` | |
| Safe termination | VERIFIED (ledger) | `::test_terminate_active_worker_keeps_its_slot_until_the_stop_is_confirmed`, `::test_terminate_finished_worker_is_confirmed` | the native stop is the host's |
| Automatic replacement | VERIFIED | `::test_transfer_picks_a_replacement_and_briefs_it`, `::test_transfer_without_a_replacement_points_to_the_factory` | |
| Transfer of unfinished assignments | VERIFIED | `::test_transfer_to_a_named_template`, `::test_refused_transfer_leaves_the_old_worker_running`, `integration/test_cli_workforce.py::test_split_then_terminate_and_transfer` | |
| Knowledge and audit preserved | VERIFIED | `::test_terminate_failed_worker_records_a_failure_lesson`; suspension, not deletion, on expiry; `audit verify` in `integration/test_cli_workforce.py::test_factory_fills_a_gap_and_recruits` | |
| Owner approval where governance requires it | VERIFIED | factory widening needs `factory_register`; retiring and quarantine release stay owner-only: `::test_rehabilitation_input_checks` | |
| Native platform constraints respected | VERIFIED (by design) | no code path starts or stops a native worker; admission and the runtime hooks stay the gate | not run in a live host session |

## V4.0 Phase 5: Self-improvement engine

See [docs/IMPROVE.md](../docs/IMPROVE.md). AgentOS never calls a model: hypotheses are
rule-based or the host's, and what is enforced is how a change earns promotion. Paid spend
stays zero; trials are ordinary admissions under the same limits and budgets.

| Requirement | Status | Evidence | Open |
| --- | --- | --- | --- |
| 1. Collect outcomes, measurements, evidence | VERIFIED | `unit/test_improve.py::test_accepting_a_task_runs_a_retrospective` (run by `boss accept` and `boss deliver`) | |
| 2. Successful and unsuccessful strategies | VERIFIED | same test (`successful` entry); thresholds 85 and 70 | hand-picked |
| 3. Recurring weaknesses | VERIFIED | `::test_retro_diagnoses_weaknesses_and_proposes_a_testable_change`, `::test_recurring_capability_mismatches_suggest_a_recruitment_policy` | |
| 4. Improvement hypotheses | VERIFIED (rule-based) | same tests | not model-written |
| 5. Improved prompts, configurations, skills, workflows | VERIFIED | `improve propose --template/--policy/--from-retro`: `integration/test_cli_improve.py::test_a_template_experiment_runs_to_promotion` | skills improve via validated memory, not by editing SKILL.md |
| 6. Isolated candidate versions | VERIFIED | `::test_the_challenger_is_an_isolated_candidate` | |
| 7. Evaluate against the baseline | VERIFIED | `::test_a_better_challenger_is_promoted_into_the_champion`, `::test_trials_are_blind_and_each_arm_runs_a_case_once` | |
| 8. Representative and held-out cases | VERIFIED | `::test_an_experiment_needs_enough_cases`, `::test_a_weaker_challenger_is_rejected_and_remembered` (held-out loss rejects) | 3 + 2 cases is a small sample |
| 9. Security and regression tests | VERIFIED | `::test_a_failing_gate_blocks_promotion`; challenger re-validated at decision | the gate runs whatever command the host names |
| 10. Independent evaluation | VERIFIED | `::test_grades_must_be_independent_and_cite_the_case_evidence`; two evaluators required: `::test_decide_refuses_while_the_evidence_is_incomplete` | evaluator identity unauthenticated |
| 11. Promote validated improvements | VERIFIED | `::test_a_better_challenger_is_promoted_into_the_champion`, `::test_a_better_policy_is_promoted_then_monitored` | |
| 12. Reject ineffective changes | VERIFIED | `::test_a_weaker_challenger_is_rejected_and_remembered`, `::test_a_flagged_trial_blocks_promotion`, `::test_an_abandoned_trial_counts_as_a_failure` | |
| 13. Monitor subsequent performance | VERIFIED | `::test_a_holding_improvement_is_adopted`, `::test_a_champion_changed_by_hand_supersedes_the_monitor` | |
| 14. Roll back regressions | VERIFIED | `::test_a_regression_after_promotion_is_rolled_back`, `::test_a_better_policy_is_promoted_then_monitored` | |
| 15. Preserve validated learning | VERIFIED | promoted: validated org procedural memory; rejected and rolled back: failure memory (same tests) | |
| Champion versus challenger | VERIFIED | all of the above | |
| No evaluation manipulation | VERIFIED | grades must cite the case's AgentOS-run evidence, come from neither arm's template, and abandoned trials count as failures | |
| No benchmark leakage | VERIFIED | `::test_held_out_cases_are_hidden_from_listings_and_the_audit`, `::test_a_challenger_that_copies_a_held_out_case_is_refused`, `::test_used_held_out_cases_no_longer_count_as_held_out`, `::test_cases_added_after_the_experiment_do_not_count` | textual check; paraphrases pass |
| No unauthorized self-modification | VERIFIED | `::test_experiments_cannot_touch_permissions_or_security`, `unit/test_policy.py::test_sensitive_or_unknown_names_are_not_tunable`, `::test_values_must_stay_within_bounds`, `integration/test_cli_improve.py::test_replacing_a_working_template_needs_the_owner` | |
| May improve recruitment, staffing, planning, skills, context, non-sensitive architecture | PARTIAL | recruitment weights (`unit/test_policy.py::test_recruitment_ranks_with_the_stored_and_overridden_weights`); staffing, planning and context through lead/planner instructions; skills through memory | no architectural component other than recruitment weights is tunable yet |
| Never ownership, security boundaries, approvals, hard limits | VERIFIED (by design) | none of them is in `policy.REGISTRY` or the tunable template fields; refused as `not_tunable` | |

## V4.0 Phase 6: Host integration

See [docs/HOSTS.md](../docs/HOSTS.md) for the compatibility reports. Versions checked on
2026-11-27: codex-cli 0.171.0 and the second host 2.1.181. The current official documentation
for both was read the same day (plugin layout, hooks, agents, instructions files).

| Requirement | Status | Evidence | Open |
| --- | --- | --- | --- |
| Dedicated native adapters for both platforms | VERIFIED | `src/agentos/adapters.py` (Codex built in; second host from a git-excluded profile): `unit/test_adapters.py::test_codex_needs_no_profile_and_the_other_host_does`, `::test_install_writes_the_plugin_and_records_it` | |
| Installed versions and official docs checked | VERIFIED | `agentos host list` reads each CLI's `--version`; findings in HOSTS.md (Codex manifest fallback path, `max_threads` alias, trusted plugin hooks; `Agent` is the second host's spawn tool) | |
| Canonical definitions, per-platform generators | VERIFIED | `definitions/` feeds `gen/codex.py` and `gen/host.py`; `unit/test_gen.py::test_committed_codex_plugin_is_up_to_date` | |
| Global installation | VERIFIED | `scripts/install.ps1` (`integration/test_install_script.py`) and `agentos host install`; Codex accepted the installed folder as a marketplace, the second host validated it | registering with the host is the user's step |
| Per-project activation | VERIFIED | `project activate` plus `host bootstrap`: `unit/test_adapters.py::test_bootstrap_manages_only_its_own_block`, `::test_bootstrap_needs_an_active_project` | |
| Concise bootstrap instructions | VERIFIED | a short managed block; `::test_bootstrap_creates_and_removes_a_file_of_its_own` | |
| Native skills | VERIFIED | `skills/agentos/SKILL.md` in both plugins; every command in it parses (`unit/test_skill_commands.py`) | |
| Native agents | VERIFIED | Codex custom agent TOML files; second host agent Markdown with front matter, accepted by its validator | |
| Supported hooks | VERIFIED | PreToolUse (spawn tool), SubagentStart, SubagentStop for both; Codex discovery test; second host live gate (Phase 2) | Codex live spawn BLOCKED |
| Shared persistent intelligence | VERIFIED | one ledger for both hosts; memory written under one host is found under the other: `integration/test_cli_host.py::test_work_and_learning_cross_hosts_both_ways` | |
| Safe cross-platform handovers | VERIFIED | same test, both directions; single claim, Git warnings, redaction (`unit/test_handover.py`) | |
| Configuration drift detection | VERIFIED | `::test_drift_finds_hand_edits_deletions_stale_definitions_and_host_updates`, `integration/test_cli_host.py::test_install_drift_rollback_and_bootstrap`; also run against a real install folder | |
| Reversible updates | VERIFIED | `::test_update_backs_up_and_rollback_restores_exactly`, `::test_uninstall_keeps_files_you_edited`, `::test_install_refuses_a_folder_it_does_not_own` | |
| ECC compatibility | VERIFIED (static) | `host check cc` against the installed ECC plugin: compatible; `::test_check_reports_shared_hooks_and_names_but_stays_compatible`, `::test_check_flags_a_second_agentos_install` | no live session with both loaded |
| Real task Codex to second host | BLOCKED | ledger path VERIFIED (`[codex-cc]`); a live Codex session needs quota this account does not have | run `tests/live` when quota returns |
| Real task second host to Codex | BLOCKED | ledger path VERIFIED (`[cc-codex]`); same blocker | |
| No raw conversation history transferred | VERIFIED | handovers hold structured fields only; the test asserts no transcript fields | |
