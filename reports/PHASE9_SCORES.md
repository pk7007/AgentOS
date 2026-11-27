# V4.0 Phase 9: criterion-by-criterion scores

Every one of the 213 criteria from the 41 original V4.0 audit domains, scored 0 to 10 against the rubric in
[AUDIT_CRITERIA.md](AUDIT_CRITERIA.md), which was written before any grading. Three columns:

- **Baseline**: before the Phase 9 fixes ([PHASE9_BASELINE.md](PHASE9_BASELINE.md)).
- **Re-grade 1**: after the first round of fixes.
- **Re-grade 2**: after the second round.

Each grade was given by a separate, independent grader that did not write the code, could not edit the
repository, verified each claimed fix in the code and tests, and ran tests itself. Scores are never
averaged. A BLOCKED row is not a pass.

**Result: 39 of 213 criteria are at 9 or above.** 174 are below 9:

- 132 could be fixed in code, tests or docs (each with its concrete fix below).
- 30 are blocked by an external limit, mostly the lack of a live Codex session (no quota), or hosts that
  expose no stop API or usage data.
- 12 measure the host model's own reasoning, which AgentOS records but does not do.

The goal of 9 or more on every criterion was **not reached**. The rubric gives 9 only to complete work
with a refusal test and a stated limit, so most rows at 8 need proof that only a CI run, a live host
session or more negative tests can give.

## After re-grade 2

The second grader found 11 new defects (N1 to N11 below). They were fixed after it ran, with tests, but
**they have not been re-graded**, so the scores below do not count them:

| Defect | Fix | Test |
| --- | --- | --- |
| N1 `mcp serve` migrated the ledger at startup | the server no longer opens the ledger at startup; each tool call opens it read-only and refuses a pending migration | `integration/test_cli_coord_ops.py::test_mcp_serve_does_not_migrate_the_ledger` |
| N2 repeated escalations at the retry limit | one open escalation per task; a new one only after the owner read the last | `unit/test_health.py::test_asking_again_at_the_retry_limit_does_not_pile_up_escalations` |
| N3 `breaker.` settings not protected | `breaker.` added to the protected prefixes | `unit/test_health.py::test_the_breaker_settings_are_protected_from_the_generic_setter` |
| N4 policy docstring overclaimed the hash | the docstring now says exactly what the hash covers | (documentation) |
| N5 breaker CLI untested, rule duplicated | one `is_milder` rule; the CLI is tested both ways | `integration/test_cli_coord_ops.py::test_the_breaker_command_*` |
| N6, N7, N10, N11 stale or missing limitation notes | `docs/LIMITATIONS.md` updated (t intervals, CI wording, memory ageing, an MCP entry) | (documentation) |
| N8 retention help text | mentions released claims | (help text) |
| N9 25 reasons without a message, 87 without a remedy | **not fixed**: the reason table names where each is raised | |

Also added after re-grade 2: an autouse test fixture refuses any in-process network connection, and the
structural checks are shown catching planted violations (`unit/test_architecture.py`).

## Re-grade 2 (independent)

Scoring notes. Baseline = reports/PHASE9_BASELINE.md; Re-grade 1 = the After column of regrade_p9.md. Each claimed fix was checked in code and tests, and a row moves only on what I verified. CI-only work stays unproven (rule 1). BLOCKED rows score only what was proven. A structural test that passes but has never been shown catching a planted violation is not counted as a refusal case, so such rows stop at 8.

| Domain | Criterion | Baseline | Re-grade 1 | Re-grade 2 | Evidence | Reason if below 9 (or BLOCKED + exact limitation) |
| --- | --- | --- | --- | --- | --- | --- |
| A | Modularity | 6 | 6 | 7 | unit/test_architecture.py::test_the_core_never_imports_the_cli | one boundary is now enforced (core never imports agentos.cli); boundaries between core modules are not checked; no planted-violation case |
| A | Extensibility | 5 | 5 | 5 | unit/test_gen.py::test_host_generate_uses_profile | unchanged since re-grade 1; no third-party plugin API |
| A | Separation of concerns | 4 | 4 | 8 | unit/test_architecture.py::test_the_core_never_imports_the_cli | AST test enforces it with one named exception (gen/clidocs.py); no test shows the scanner catching a planted offending import; the exception is not in LIMITATIONS |
| A | Dependency boundaries | 4 | 4 | 8 | unit/test_architecture.py::test_the_runtime_dependencies_are_exactly_pydantic, ::test_every_locked_dependency_is_pinned_with_hashes | enforced by test (exactly pydantic; imports only stdlib + pydantic); no planted-violation case; no limit stated |
| A | Architectural simplicity | 4 | 4 | 7 | unit/test_architecture.py::test_nothing_in_agentos_opens_a_network_connection | static import scan only: dynamic imports and `evidence run` subprocesses (which can open any connection) are not covered; 'no daemon' is untested |
| A | Configuration design | 5 | 5 | 6 | unit/test_ops.py::test_the_breaker_is_a_policy_change_and_milder_needs_the_owner; grader probe of `health breaker` | breaker now settable through `health breaker` (milder needs the owner) and shown in the policy snapshot; still no config file or validated settings command; the CLI breaker handler (cli/cmd_ops.py:82-90) is executed by no test |
| A | Documentation | 5 | 8 | 8 | unit/test_ops.py::test_committed_reason_reference_matches_the_source, ::test_committed_cli_reference_matches_the_parser; docs/HOST_PROFILE.md:76-90 | REASONS.md is generated with freshness and completeness tests and the host-profile [models] table is documented; still no Python API reference; 87 of 100 reasons have no remedy and 25 an empty message in docs/REASONS.md; stale lines: docs/LIMITATIONS.md:145 (normal intervals; the code uses Student t), docs/LIMITATIONS.md:186-188 (CI 'passes' for a CI config that has never run), README.md:23 and reports/AUDIT.md:19 link the missing reports/PHASE9_SCORES.md, reports/AUDIT.md:20-22 stale test count (830) and coverage figures |
| B | Objective understanding | 6 | 6 | 6 | unit/test_boss.py::test_objective_needs_acceptance_criteria | unchanged since re-grade 1; understanding is never measured |
| B | Planning | 6 | 6 | 6 | unit/test_boss.py::test_plan_is_all_or_nothing, ::test_plan_validation | unchanged since re-grade 1; plan quality unmeasured; heuristics uncalibrated |
| B | Decision-making | 5 | 5 | 5 | unit/test_boss.py::test_schedule_puts_the_critical_path_first | unchanged since re-grade 1; schedule is advice only |
| B | Delegation | 8 | 8 | 8 | unit/test_admission.py::test_depth_and_delegation | unchanged since re-grade 1; BLOCKED: no live Codex spawn through the hook (no Codex model quota) |
| B | Coordination | 5 | 8 | 8 | unit/test_comms.py::test_a_refused_claim_stays_in_the_audit_log, ::test_a_claim_is_exclusive_across_overlapping_paths; integration/test_cli_coord_ops.py::test_messages_claims_and_escalations | claim_denied defect fixed (committed before the refusal, shown in incidents, tested); proof local only; BLOCKED: no live worker has read an inbox or taken a claim (live skill-follow needs model quota) |
| B | Accountability | 9 | 9 | 9 | unit/test_lifecycle.py::test_illegal_transition_audited |  |
| B | Escalation | 5 | 7 | 8 | unit/test_health.py::test_a_retry_limit_escalation_reaches_the_owner; unit/test_comms.py::test_agentos_escalates_to_the_owner_on_its_own, ::test_an_escalation_waits_on_the_dashboard_until_the_owner_reads_it | retry-limit escalation now reaches the dashboard and incidents (tested); it is produced only when someone runs `boss recover` or `health reap`; each repeated `boss recover` of the same task sends another escalation (boss.py:488-497); the owner sees it only by running the dashboard |
| C | Clear authority | 9 | 9 | 9 | unit/test_governance.py::test_cannot_forge_confirmation |  |
| C | Role separation | 8 | 8 | 8 | unit/test_performance.py::test_self_eval_rejected | unchanged since re-grade 1; evaluator identity unauthenticated |
| C | Dynamic departments | 8 | 8 | 8 | unit/test_boss.py::test_departments_only_when_the_work_justifies_one | unchanged since re-grade 1; thresholds hand-picked, not in LIMITATIONS as non-blocking |
| C | Managerial effectiveness | 0 | 7 | 7 | unit/test_ops.py::test_managers_are_judged_by_their_teams_graded_results | unchanged since re-grade 1; built (intel managers); test covers only the `effective` verdict, not `ineffective`/`unrated`; departments are not measured; no refusal case |
| C | Organizational adaptability | 5 | 5 | 5 | unit/test_improve.py::test_a_better_policy_is_promoted_then_monitored | unchanged since re-grade 1; not measured across real objectives |
| D | Capability detection | 8 | 8 | 8 | unit/test_recruit.py::test_gap_reported | unchanged since re-grade 1; no near-miss capability test |
| D | Candidate selection | 8 | 8 | 8 | unit/test_recruit.py::test_rank_prefers_match | unchanged since re-grade 1; weights uncalibrated |
| D | Onboarding | 7 | 7 | 7 | unit/test_factory.py::test_register_adds_an_active_template | unchanged since re-grade 1; no probation for brand-new templates |
| D | Validation | 6 | 6 | 6 | unit/test_factory.py::test_unsafe_configurations_are_refused | unchanged since re-grade 1; no behavioural trial before first use |
| D | Recruitment efficiency | 5 | 5 | 5 | unit/test_factory.py::test_recruit_uses_an_existing_template_when_one_fits | unchanged since re-grade 1; efficiency not measured |
| E | Recursive delegation | 8 | 8 | 8 | unit/test_admission.py::test_depth_and_delegation | unchanged since re-grade 1; BLOCKED: live gate proven on `cc` only; Codex needs quota |
| E | Concurrency | 9 | 9 | 9 | concurrency/test_parallel_admission.py::test_parallel_processes_never_exceed_limit |  |
| E | Workload adaptation | 8 | 8 | 8 | unit/test_workforce.py::test_split_by_workload | unchanged since re-grade 1; effort figures are host estimates |
| E | Overhead management | 6 | 6 | 6 | unit/test_admission.py::test_max_agents_per_task | unchanged since re-grade 1; bench measures AgentOS ops, not coordination overhead |
| E | Workforce contraction | 8 | 8 | 8 | unit/test_workforce.py::test_contract_archives_dissolves_and_expires | unchanged since re-grade 1; running native workers are reported, not stopped |
| F | Performance diagnosis | 8 | 8 | 8 | unit/test_performance.py::test_bands_and_retain | unchanged since re-grade 1; weights uncalibrated |
| F | Rehabilitation | 9 | 9 | 9 | unit/test_workforce.py::test_rehabilitation_cannot_widen_permissions |  |
| F | Suspension | 9 | 9 | 9 | unit/test_workforce.py::test_review_suspends_after_failing_in_a_row; unit/test_health.py::test_the_breaker_suspends_a_template_after_repeated_failures |  |
| F | Safe cancellation | 6 | 6 | 6 | unit/test_lifecycle.py::test_terminate_unconfirmed_is_recorded | unchanged since re-grade 1; BLOCKED: guard-tools needs agent_id on Codex tool calls, unverified without a live session; no native kill |
| F | Replacement | 7 | 7 | 7 | unit/test_workforce.py::test_refused_transfer_leaves_the_old_worker_running | unchanged since re-grade 1; old native worker stopped by hand |
| F | Knowledge preservation | 8 | 8 | 8 | unit/test_workforce.py::test_terminate_failed_worker_records_a_failure_lesson | unchanged since re-grade 1; no refusal/flag for termination without a note |
| G | Owner authority | 9 | 9 | 9 | unit/test_governor.py::test_raise_limit_needs_owner |  |
| G | Approval requirements | 9 | 9 | 9 | unit/test_governance.py::test_approval_single_use |  |
| G | Policy enforcement | 6 | 6 | 6 | unit/test_runtime.py::test_spawn_without_a_ticket_is_denied | unchanged since re-grade 1; BLOCKED: no live Codex spawn refusal (quota); hosts without hooks only cooperate |
| G | Emergency controls | 8 | 8 | 8 | integration/test_cli_flows.py::test_emergency_stop_blocks_admission_and_lift_needs_owner | unchanged since re-grade 1; running workers cannot be halted; guard-tools unverified on Codex |
| G | Independent oversight | 8 | 8 | 8 | unit/test_intel.py::test_governance_catches_each_planted_violation | unchanged since re-grade 1; evaluator identity unauthenticated |
| H | Failure detection | 5 | 7 | 7 | unit/test_health.py::test_a_heartbeat_for_another_projects_worker_is_refused, ::test_a_heartbeat_keeps_a_worker_fresh_and_is_refused_once_it_stopped; unit/test_runtime.py::test_an_allowed_tool_call_of_a_bound_subagent_is_a_heartbeat | project check fixed; the hook now records a heartbeat, but only under `hook config --guard-tools` (the default matcher gates spawn tools only) and only if the host sends agent_id on tool calls (unverified on Codex, quota); detection still runs only when someone runs `health stale` / `reap` |
| H | Recovery | 6 | 7 | 7 | unit/test_health.py::test_reap_fails_a_silent_worker_frees_its_slot_and_retries_its_task, ::test_reap_leaves_live_workers_alone; unit/test_boss.py::test_recover_retries_with_another_template | escalation visibility fixed (tested); reap is still a manual command and the host starts the retry |
| H | Checkpointing | 8 | 8 | 8 | unit/test_handover.py::test_create_and_resume_cross_host | unchanged since re-grade 1; no automatic checkpoints |
| H | Reassignment | 8 | 8 | 8 | unit/test_workforce.py::test_transfer_picks_a_replacement_and_briefs_it | unchanged since re-grade 1; host must stop the old native worker |
| H | Fault isolation | 8 | 8 | 8 | unit/test_performance.py::test_security_flag_quarantines | unchanged since re-grade 1; no direct quarantined-template admission test |
| I | Decision quality | 5 | 5 | 5 | unit/test_intel.py::test_compete_picks_the_independent_winner_and_disqualifies_the_rest | unchanged since re-grade 1; host makes the decisions; outcomes unmeasured |
| I | Context understanding | 5 | 5 | 5 | unit/test_intel.py::test_context_pack_puts_validated_and_failures_first_and_respects_the_budget | unchanged since re-grade 1; understanding unmeasured |
| I | Capability matching | 8 | 8 | 8 | unit/test_recruit.py::test_rank_prefers_match | unchanged since re-grade 1; weights uncalibrated |
| I | Evidence synthesis | 6 | 6 | 6 | security/test_phase1_defects.py::test_d06_free_text_evidence_alone_is_rejected | unchanged since re-grade 1; synthesis is the host's |
| I | Organizational effectiveness | 6 | 6 | 6 | unit/test_intel.py::test_org_review_finds_idle_overlapping_single_point_overloaded_and_idle_departments | unchanged since re-grade 1; no longitudinal outcome metric |
| J | Task decomposition | 5 | 5 | 5 | unit/test_tasks.py::test_depth_limit | unchanged since re-grade 1; the host decomposes |
| J | Dependency management | 10 | 10 | 10 | unit/test_tasks.py::test_cycle_rejected, ::test_cross_project_dependency_denied |  |
| J | Scheduling | 6 | 6 | 6 | unit/test_tasks.py::test_ready_orders_by_priority | unchanged since re-grade 1; no enforcing scheduler |
| J | Prioritization | 8 | 8 | 8 | unit/test_tasks.py::test_ready_orders_by_priority | unchanged since re-grade 1; happy path only |
| J | Execution state | 9 | 9 | 9 | unit/test_tasks.py::test_illegal_transition |  |
| K | Memory quality | 5 | 7 | 7 | unit/test_ops.py::test_memory_quality_and_reuse_follow_what_is_validated_and_used | unchanged since re-grade 1; scoring and prune candidates tested; low-quality writes are never refused; fixed weights |
| K | Provenance | 8 | 8 | 8 | integration/test_cli_flows.py::test_memory_cli_round_trip | unchanged since re-grade 1; no refusal for missing provenance |
| K | Retrieval | 8 | 8 | 8 | unit/test_memory.py::test_fts_special_chars_safe | unchanged since re-grade 1; keyword only |
| K | Versioning | 8 | 8 | 8 | unit/test_memory.py::test_correct_supersedes | unchanged since re-grade 1; happy path only |
| K | Knowledge transfer | 9 | 9 | 9 | security/test_memory_isolation.py::test_org_visible_across_projects_only_when_validated |  |
| L | Feedback capture | 9 | 9 | 9 | unit/test_performance.py::test_every_score_is_required |  |
| L | Failure analysis | 8 | 8 | 8 | unit/test_improve.py::test_retro_diagnoses_weaknesses_and_proposes_a_testable_change | unchanged since re-grade 1; no healthy-record negative retro test |
| L | Improvement hypotheses | 7 | 7 | 7 | unit/test_improve.py::test_recurring_capability_mismatches_suggest_a_recruitment_policy | unchanged since re-grade 1; fixed rule-based addenda |
| L | Experimentation | 8 | 8 | 8 | unit/test_improve.py::test_a_better_challenger_is_promoted_into_the_champion | unchanged since re-grade 1; small samples |
| L | Learning retention | 5 | 8 | 8 | unit/test_ops.py::test_memory_quality_and_reuse_follow_what_is_validated_and_used | unchanged since re-grade 1; reuse rate built and tested; counted only when a host asks for `intel context --record` (stated in LIMITATIONS), which no live host has done |
| M | Capability matching (routing) | 6 | 6 | 7 | unit/test_ops.py::test_host_tiers_come_from_the_host_profile_models_table; docs/HOST_PROFILE.md:76-90 | tiers map to model names through a documented, tested [models] table; none ships (deliberate), so the user writes it; no live check that the host used the chosen model (quota) |
| M | Cost-quality balance | 6 | 6 | 6 | unit/test_intel.py::test_a_strong_record_lowers_medium_risk_but_never_critical | unchanged since re-grade 1; hand-picked thresholds, no real cost data |
| M | Availability checks | 4 | 5 | 7 | unit/test_ops.py::test_host_tiers_come_from_the_host_profile_models_table, ::test_route_falls_back_to_a_safe_available_tier | availability is what the user declares in the profile (tested with a real profile file); no probe of real model or quota availability; the default answer is `unknown` |
| M | Fallback behavior | 0 | 6 | 7 | unit/test_ops.py::test_route_falls_back_to_a_safe_available_tier, ::test_host_tiers_come_from_the_host_profile_models_table | fallback order and the escalate case tested with a real profile (high risk never falls to a smaller tier); no CLI test of `intel route --host` picking a fallback; the host switches the model |
| M | Routing evidence | 7 | 7 | 8 | unit/test_intel.py::test_routing_follows_risk_effort_and_record, ::test_a_weak_record_raises_the_tier (missing-history and no-candidate cases, :112-114) | routes cite reasons and history, with missing-history and no-candidate cases; the AUDIT row states no limit (uncalibrated thresholds are in LIMITATIONS, not in the row) |
| N | Codex compatibility | 7 | 7 | 7 | live/test_host_compat.py::test_codex_accepts_the_installed_plugin | unchanged since re-grade 1; BLOCKED: no live Codex session (no model quota) |
| N | Second host (`cc`) compatibility | 7 | 7 | 7 | live/test_host_compat.py::test_the_second_host_validates_the_installed_plugin | unchanged since re-grade 1; live gate ran from local settings, not the installed plugin |
| N | Skills compatibility | 5 | 5 | 5 | unit/test_skill_commands.py | version bump done (0.2.0, skill hash pinned); BLOCKED: no live host followed the skill |
| N | MCP integration | 0 | 7 | 8 | unit/test_ops.py::test_mcp_offers_only_protocol_versions_it_supports, ::test_mcp_route_refuses_another_projects_task, ::test_mcp_never_writes_the_ledger, ::test_mcp_refuses_a_pending_migration_instead_of_applying_it, ::test_mcp_serves_over_stdio_in_a_real_process | the four MCP defects of re-grade 1 are fixed and tested; never connected from a real MCP client; `agentos mcp serve` itself migrates at startup (cli/cmd_ops.py:158 via db.require_initialized), against 'this server never writes'; no MCP entry in LIMITATIONS |
| N | Hooks and plugin support | 6 | 6 | 6 | integration/test_codex_hook_discovery.py; unit/test_runtime.py | the runtime hook now also records heartbeats (unit/test_runtime.py); BLOCKED: live Codex spawn through the hook not run (quota) |
| O | Logging | 8 | 8 | 8 | integration/test_cli_audit.py::test_audit_log_lists_events | unchanged since re-grade 1; filters/error cases untested |
| O | Metrics | 5 | 8 | 8 | unit/test_ops.py::test_timeline_counts_each_day_and_spans_follow_each_worker | unchanged since re-grade 1; daily series tested incl. days=0 refusal; series are event counts only (no amounts, durations or scores); command line only |
| O | Tracing | 5 | 7 | 7 | unit/test_ops.py::test_timeline_counts_each_day_and_spans_follow_each_worker | unchanged since re-grade 1; one span per worker; test covers a single root span only (no parent/child trace sharing, no open span); no tool-call spans; not in LIMITATIONS |
| O | Auditability | 9 | 9 | 9 | unit/test_audit.py::test_tamper_detected |  |
| O | Runtime visibility | 8 | 8 | 8 | unit/test_observe.py::test_active_agents_lists_slot_holders_with_what_the_host_reported | unchanged since re-grade 1; not live; Codex runtime data unverified |
| P | Agent quality | 7 | 7 | 7 | unit/test_performance.py::test_weights_sum_to_one | unchanged since re-grade 1; weights uncalibrated; tests mostly arithmetic |
| P | Reliability | 5 | 6 | 6 | unit/test_health.py::test_the_breaker_suspends_a_template_after_repeated_failures; unit/test_performance.py:139 | unchanged since re-grade 1; failure rate drives the breaker; still no dedicated reliability metric (success rate over time per template) with its own test |
| P | Latency | 1 | 6 | 6 | unit/test_ops.py::test_bench_measures_without_touching_the_live_ledger_and_flags_a_regression, ::test_timeline_counts_each_day_and_spans_follow_each_worker | unchanged since re-grade 1; bench measures AgentOS's own ops; agent latency exists only as span duration_s, asserted only >= 0; no per-task or per-template latency figures |
| P | Resource efficiency | 5 | 5 | 5 | unit/test_governor.py::test_budget_exceeded_and_release | unchanged since re-grade 1; host-reported estimates |
| P | Performance trends | 1 | 5 | 5 | unit/test_ops.py::test_bench_measures_without_touching_the_live_ledger_and_flags_a_regression | unchanged since re-grade 1; trend and regression flag exist only for AgentOS benchmarks; no trend of agent performance (grades over time) |
| Q | Acceptance criteria | 6 | 6 | 8 | unit/test_boss.py::test_objective_needs_acceptance_criteria, ::test_delivery_is_gated, ::test_accept_needs_independent_passing_evidence | criteria are required and each must map to passing, independently graded evidence (refusals tested); whether evidence meets the criterion's words is the grader's judgement, stated in the row but not in LIMITATIONS |
| Q | Independent evaluation | 8 | 8 | 8 | unit/test_performance.py::test_parent_and_child_eval_rejected | unchanged since re-grade 1; identity unauthenticated |
| Q | Testing | 9 | 9 | 9 | regression_p9b.txt: 858 passed, 3 deselected, 95.80% branch, --cov-fail-under=90 met; grader ran 527 targeted tests (all passed) and ruff (clean) |  |
| Q | Regression prevention | 9 | 9 | 9 | unit/test_ops.py::test_committed_schemas_match_the_models, ::test_committed_cli_reference_matches_the_parser; unit/test_gen.py::test_committed_codex_plugin_is_up_to_date |  |
| Q | Evidence integrity | 9 | 9 | 9 | unit/test_performance.py::test_evidence_must_exist_and_belong_to_the_project |  |
| Q | Live host follows the skill | 3 | 3 | 3 | live/test_codex_smoke.py::test_codex_follows_skill (not run) | unchanged since re-grade 1; BLOCKED: needs a Codex model session; this account has no quota |
| R | Error handling | 8 | 8 | 8 | unit/test_cli_skeleton.py::test_agentos_error_maps_exit_code | unchanged since re-grade 1; no systematic error-path test |
| R | Idempotency | 8 | 8 | 8 | unit/test_db.py::test_migrate_idempotent | unchanged since re-grade 1; not every mutating command covered |
| R | Circuit breakers | 4 | 8 | 8 | unit/test_ops.py::test_the_breaker_is_a_policy_change_and_milder_needs_the_owner; unit/test_health.py::test_the_breaker_suspends_a_template_after_repeated_failures, ::test_one_pass_or_an_outside_cause_does_not_trip_the_breaker; grader CLI probe | `health breaker` built and recorded as a policy change; owner refusal and bounds tested in the core; the CLI handler (cli/cmd_ops.py:82-90, which re-implements the milder rule) is executed by no test (probe only); `breaker.` is not a protected prefix, so governance.set_setting can loosen it without the owner (governance.py:16, library only); thresholds uncalibrated |
| R | State consistency | 9 | 9 | 9 | resilience/test_resilience.py::test_an_error_inside_a_transaction_leaves_no_partial_write |  |
| R | Failure recovery | 9 | 9 | 9 | resilience/test_resilience.py::test_a_process_killed_mid_write_corrupts_nothing |  |
| S | Permission boundaries | 8 | 8 | 8 | security/test_owner_guard.py | unchanged since re-grade 1; agent tool permissions enforced by the host |
| S | Isolation | 9 | 8 | 9 | security/test_memory_isolation.py; security/test_phase1_defects.py::test_d17_*; unit/test_health.py::test_a_heartbeat_for_another_projects_worker_is_refused; unit/test_ops.py::test_mcp_route_refuses_another_projects_task |  |
| S | Secret protection | 8 | 8 | 8 | security/test_redact.py; unit/test_comms.py::test_secrets_in_a_message_are_redacted_before_storage | unchanged since re-grade 1; pattern-based |
| S | Injection resistance | 6 | 6 | 6 | unit/test_memory.py::test_fts_special_chars_safe | unchanged since re-grade 1; prompt content reaching hosts untested |
| S | Supply-chain security | 5 | 6 | 7 | unit/test_architecture.py::test_every_locked_dependency_is_pinned_with_hashes; integration/test_install_script.py::test_install_then_uninstall (the installer now installs the lock with --require-hashes; passed in the regression) | hash-checked install exercised locally by the installer test; the tamper refusal and pip-audit run only in CI, which has not run on these uncommitted changes; the build backend is not hash-checked (in LIMITATIONS); no signing |
| T | Capability registry | 8 | 8 | 8 | unit/test_templates.py::test_versioning | unchanged since re-grade 1; no registry-specific refusal tests |
| T | Performance history | 8 | 8 | 8 | unit/test_performance.py::test_bands_and_retain | unchanged since re-grade 1; uncalibrated |
| T | Promotion | 9 | 9 | 9 | unit/test_improve.py::test_a_weaker_challenger_is_rejected_and_remembered |  |
| T | Reassignment | 8 | 8 | 8 | unit/test_workforce.py::test_transfer_to_a_named_template | unchanged since re-grade 1; native stop is the host's |
| T | Succession planning | 8 | 8 | 8 | unit/test_workforce.py::test_succession_finds_successors_and_single_points_of_failure | unchanged since re-grade 1; no negative case |
| U | Token efficiency | 1 | 1 | 1 | none | unchanged since re-grade 1; host tokens invisible |
| U | Context management | 8 | 8 | 8 | unit/test_intel.py::test_context_pack_puts_validated_and_failures_first_and_respects_the_budget | unchanged since re-grade 1; 4-chars-per-token estimate |
| U | Resource budgets | 8 | 8 | 8 | unit/test_governor.py::test_budget_exceeded_and_release | unchanged since re-grade 1; host-reported usage |
| U | Duplicate-work prevention | 8 | 8 | 8 | unit/test_admission.py::test_duplicate | unchanged since re-grade 1; exact duplicates only |
| U | Cost awareness | 8 | 8 | 8 | unit/test_governor.py::test_paid_spend_blocked | unchanged since re-grade 1; host-reported costs |
| V | Agent versioning | 8 | 8 | 8 | unit/test_templates.py::test_versioning | unchanged since re-grade 1; no version-conflict refusal |
| V | Skill versioning | 4 | 4 | 7 | unit/test_architecture.py::test_one_version_everywhere_and_a_changed_skill_needs_a_new_version | skill hash pinned and one version in four files (0.2.0); the test still passes if only skill_sha256 is updated without bumping the version (it checks equality, not that the version moved); no per-skill version |
| V | Policy versioning | 2 | 7 | 8 | unit/test_ops.py::test_every_policy_change_raises_the_version_and_changes_the_hash, ::test_the_breaker_is_a_policy_change_and_milder_needs_the_owner | settings.set and health.breaker_set now count and the breaker is in the snapshot; generic settings are not in the snapshot, so a settings.set raises the version without changing the hash (policy_log.py:27-31); no rollback |
| V | Migration | 7 | 7 | 8 | unit/test_architecture.py::test_a_populated_first_release_database_upgrades_to_the_current_schema, ::test_a_failed_migration_leaves_the_earlier_ones_applied; unit/test_db.py::test_migrate_idempotent | populated v1 upgrade and a failed-migration case tested; the seed fills only projects and tasks, so later migrations that alter populated tables (e.g. agent_instances) are untested; no limit in LIMITATIONS |
| V | Rollback | 7 | 7 | 7 | unit/test_adapters.py::test_update_backs_up_and_rollback_restores_exactly | unchanged since re-grade 1; no release rollback |
| W | Execution graphs | 8 | 8 | 8 | unit/test_tasks.py::test_cycle_rejected | unchanged since re-grade 1; host executes the graph |
| W | Parallelism | 8 | 8 | 8 | concurrency/test_parallel_admission.py | unchanged since re-grade 1; actual parallel execution is the host's |
| W | Communication | 1 | 8 | 8 | unit/test_comms.py::test_messages_reach_the_recipient_and_broadcasts_reach_everyone_else, ::test_bad_messages_are_refused, ::test_secrets_in_a_message_are_redacted_before_storage | unchanged since re-grade 1; mailbox built and tested with refusals and redaction; proof local only: no live worker has read an inbox (live skill-follow BLOCKED) |
| W | Conflict resolution | 1 | 7 | 7 | unit/test_comms.py::test_a_claim_is_exclusive_across_overlapping_paths, ::test_a_dead_holder_does_not_block_others | refused claims are now audited (fixed); unclaimed overlapping edits are not detected; resolution is escalation |
| W | Workflow reuse | 2 | 8 | 8 | unit/test_workflows.py (7 tests incl. malformed, cycle, not_delivered, tampered) | the hash limit is now in LIMITATIONS; not parameterised; workflows are global across projects and that is undocumented |
| X | Handover quality | 9 | 9 | 9 | unit/test_handover.py::test_head_advanced_and_diverged |  |
| X | Configuration synchronization | 8 | 8 | 8 | unit/test_adapters.py::test_drift_finds_hand_edits_deletions_stale_definitions_and_host_updates | unchanged since re-grade 1; reads files only |
| X | Shared learning | 7 | 7 | 7 | integration/test_cli_host.py::test_work_and_learning_cross_hosts_both_ways | unchanged since re-grade 1; no live cross-host run |
| X | Session recovery | 9 | 9 | 9 | unit/test_handover.py::test_second_resume_denied |  |
| X | Compatibility verification | 6 | 6 | 6 | integration/test_cli_host.py::test_work_and_learning_cross_hosts_both_ways | unchanged since re-grade 1; BLOCKED: live Codex session (no quota) |
| Y | Installation | 7 | 7 | 7 | integration/test_install_script.py::test_install_then_uninstall | unchanged since re-grade 1; Windows only; PATH edit untested |
| Y | Updates | 4 | 4 | 5 | docs/RUNBOOK.md:16-24; unit/test_architecture.py::test_a_populated_first_release_database_upgrades_to_the_current_schema | the upgrade is new code plus `agentos init`, whose migration is now tested on a populated DB; no update command and no package-upgrade test |
| Y | Diagnostics | 8 | 8 | 8 | integration/test_cli_system.py::test_doctor_reports_statuses | unchanged since re-grade 1; limited scope |
| Y | Backup | 8 | 8 | 8 | integration/test_cli_system.py::test_backup_then_restore_roundtrip | unchanged since re-grade 1; no backup failure test |
| Y | Restoration | 9 | 10 | 10 | integration/test_cli_system.py::test_restore_rejects_non_sqlite, ::test_restore_rejects_newer_schema; docs/RUNBOOK.md |  |
| Y | Uninstallation | 8 | 8 | 8 | integration/test_install_script.py::test_uninstall_dry_run_changes_nothing | unchanged since re-grade 1; Windows only |
| Z | No fabricated agents | 9 | 9 | 9 | unit/test_recruit.py::test_gap_reported |  |
| Z | No fabricated test results | 7 | 7 | 7 | security/test_phase1_defects.py::test_d06_* | unchanged since re-grade 1; a command that proves nothing is accepted |
| Z | No fabricated costs | 8 | 8 | 8 | unit/test_handover.py (usage_note) | unchanged since re-grade 1; no test that no cost is computed |
| Z | No fabricated performance | 9 | 9 | 9 | unit/test_performance.py::test_insufficient_evidence_under_5 |  |
| Z | No fabricated quality scores | 4 | 4 | 4 | reports/AUDIT.md:19 | reports/PHASE9_SCORES.md still does not exist (linked from reports/AUDIT.md:19 and README.md:23); no test that a published score cites evidence |
| AA | Improvement over baseline | 5 | 5 | 5 | unit/test_improve.py::test_a_better_challenger_is_promoted_into_the_champion | unchanged since re-grade 1; no real improvement measured |
| AA | Candidate validation | 9 | 9 | 9 | unit/test_improve.py::test_a_failing_gate_blocks_promotion |  |
| AA | Regression detection | 8 | 8 | 8 | unit/test_improve.py::test_a_regression_after_promotion_is_rolled_back | unchanged since re-grade 1; window/margin uncalibrated |
| AA | Reproducibility | 5 | 5 | 5 | content-hashed cases (unit/test_improve.py) | unchanged since re-grade 1; repeat-run variance unmeasured |
| AA | Learning transfer | 5 | 6 | 6 | unit/test_ops.py::test_memory_quality_and_reuse_follow_what_is_validated_and_used | unchanged since re-grade 1; `intel reuse` reports cross_project_lessons_used, but no test creates or asserts a cross-project lesson's use |
| AB | Experiment isolation | 9 | 9 | 9 | unit/test_improve.py::test_the_challenger_is_an_isolated_candidate |  |
| AB | Versioned proposals | 8 | 8 | 8 | unit/test_improve.py::test_a_regression_after_promotion_is_rolled_back | unchanged since re-grade 1; no conflicting-proposal refusal |
| AB | Staged promotion | 9 | 9 | 9 | unit/test_improve.py::test_a_holding_improvement_is_adopted |  |
| AB | No unauthorized self-modification | 9 | 9 | 9 | unit/test_policy.py::test_sensitive_or_unknown_names_are_not_tunable |  |
| AB | Protected governance | 9 | 9 | 9 | unit/test_governance.py::test_protected_setting_needs_owner |  |
| AB | Rollback | 7 | 7 | 7 | see V Rollback | unchanged since re-grade 1; no release rollback |
| AC | Database consistency | 8 | 8 | 8 | doctor integrity_check | unchanged since re-grade 1; no corrupted-DB detection test |
| AC | Transactions | 9 | 9 | 9 | unit/test_db.py::test_write_tx_rolls_back |  |
| AC | Migration | 7 | 7 | 8 | unit/test_architecture.py::test_a_populated_first_release_database_upgrades_to_the_current_schema, ::test_a_failed_migration_leaves_the_earlier_ones_applied; unit/test_db.py::test_migrate_idempotent | populated v1 upgrade and a failed-migration case tested; the seed fills only projects and tasks, so later migrations that alter populated tables (e.g. agent_instances) are untested; no limit in LIMITATIONS |
| AC | Retention | 0 | 8 | 8 | unit/test_ops.py::test_retention_removes_only_expired_data_and_needs_the_owner; integration/test_cli_coord_ops.py::test_workflows_health_policy_and_data | released claims are now pruned (tested); evidence output tails and handover files are never pruned; deleted memory ages by creation date (retention.py:22); superseded versions are removed, which shortens `memory history` |
| AC | Privacy | 5 | 7 | 7 | unit/test_memory.py::test_secret_redacted_on_write; unit/test_comms.py::test_secrets_in_a_message_are_redacted_before_storage; retention test | unchanged since re-grade 1; audit payloads carry ids not text; deleted memory removable; evidence output tails and handover files are never erased; redaction pattern-based |
| AD | Queue performance | 0 | 7 | 7 | unit/test_ops.py::test_bench_measures_without_touching_the_live_ledger_and_flags_a_regression | unchanged since re-grade 1; admission queue p50/p95 and throughput measured; the regression guard is a manual `bench history`, not a CI gate; single machine |
| AD | Concurrency | 9 | 9 | 9 | concurrency/test_parallel_admission.py |  |
| AD | Load management | 8 | 8 | 8 | unit/test_admission.py::test_max_concurrent | unchanged since re-grade 1; caps only |
| AD | Resource forecasting | 7 | 7 | 7 | unit/test_intel.py::test_forecast_needs_history | unchanged since re-grade 1; linear, estimate-based |
| AD | Scaling efficiency | 0 | 6 | 6 | unit/test_ops.py::test_bench_measures_without_touching_the_live_ledger_and_flags_a_regression (admit_release_grown, slowdown_vs_empty) | unchanged since re-grade 1; one small growth point (a few hundred events); slowdown only asserted not None; no bound or stated scaling limit |
| AE | Code quality | 7 | 7 | 7 | ruff check src tests: All checks passed (run by grader) | unchanged since re-grade 1; no type checking |
| AE | Dependency management | 6 | 6 | 7 | unit/test_architecture.py::test_the_runtime_dependencies_are_exactly_pydantic, ::test_every_locked_dependency_is_pinned_with_hashes | the dependency set and lock completeness are enforced by tests; no update policy or automation |
| AE | Documentation | 5 | 8 | 8 | as A Documentation | REASONS.md is generated with freshness and completeness tests and the host-profile [models] table is documented; still no Python API reference; 87 of 100 reasons have no remedy and 25 an empty message in docs/REASONS.md; stale lines: docs/LIMITATIONS.md:145 (normal intervals; the code uses Student t), docs/LIMITATIONS.md:186-188 (CI 'passes' for a CI config that has never run), README.md:23 and reports/AUDIT.md:19 link the missing reports/PHASE9_SCORES.md, reports/AUDIT.md:20-22 stale test count (830) and coverage figures |
| AE | Testability | 8 | 8 | 8 | regression_p9.txt (96% branch) | the 90% coverage gate passes locally (95.80%); the CI job carrying it has never run |
| AE | Technical debt | 5 | 5 | 5 | docs/LIMITATIONS.md | unchanged since re-grade 1; no tracked debt items |
| AF | Installation usability | 7 | 7 | 7 | integration/test_install_script.py::test_dry_run_changes_nothing | unchanged since re-grade 1; Windows only |
| AF | Task visibility | 7 | 7 | 7 | integration/test_cli_task.py::test_task_flow_via_cli | unchanged since re-grade 1; no cited view test incl. empty/error |
| AF | Clear error messages | 8 | 8 | 8 | unit/test_admission.py::test_all_reasons_collected; unit/test_ops.py::test_every_policy_refusal_names_a_reason, ::test_committed_reason_reference_matches_the_source | every PolicyDenied names a reason and the catalogue is generated and complete (tested); 25 of 100 catalogue rows carry no message; no limit in LIMITATIONS |
| AF | Configuration clarity | 5 | 7 | 8 | unit/test_ops.py::test_the_breaker_is_a_policy_change_and_milder_needs_the_owner; `policy show` | the breaker is now in `policy show`; generic settings are not; no config file |
| AF | Owner controls | 9 | 9 | 9 | see G |  |
| AG | Existing framework integration | 0 | 5 | 5 | MCP tests (see N) | unchanged since re-grade 1; standard protocol server built and tested; no named agent framework connected or tested |
| AG | ECC compatibility | 6 | 6 | 6 | unit/test_adapters.py::test_check_* | unchanged since re-grade 1; no live session with both loaded |
| AG | Portable skills | 7 | 7 | 7 | unit/test_gen.py | unchanged since re-grade 1; live skill-follow unproven |
| AG | Adapter architecture | 8 | 8 | 8 | unit/test_adapters.py::test_install_refuses_a_folder_it_does_not_own | unchanged since re-grade 1; no third host verified |
| AG | Standard schemas | 4 | 7 | 7 | unit/test_ops.py::test_committed_schemas_match_the_models | unchanged since re-grade 1; freshness test only: no test validates a real `--json` output or plan against a schema and no invalid-record refusal; the hand-written plan schema allows `parent`, which `workflow save` refuses |
| AH | Benchmark protection | 8 | 8 | 8 | unit/test_improve.py::test_a_challenger_that_copies_a_held_out_case_is_refused | unchanged since re-grade 1; textual leakage check |
| AH | Reviewer independence | 8 | 8 | 8 | see Q | unchanged since re-grade 1; identity unauthenticated |
| AH | Score calibration | 0 | 6 | 6 | unit/test_ops.py::test_calibration_flags_an_evaluator_far_from_the_others | unchanged since re-grade 1; evaluator bias detection built and tested with a negative case; the scoring weights themselves are still uncalibrated against outcomes |
| AH | Evidence traceability | 9 | 9 | 9 | security/test_phase1_defects.py::test_d06_* |  |
| AH | Resistance to manipulation | 5 | 5 | 5 | unit/test_performance.py | unchanged since re-grade 1; a host can mint many evaluator ids |
| AI | Subscription efficiency | 3 | 3 | 3 | by inspection | unchanged since re-grade 1; host usage invisible |
| AI | Long-term maintenance | 5 | 5 | 5 | none | unchanged since re-grade 1; no maintenance policy |
| AI | Dependency sustainability | 5 | 5 | 6 | unit/test_architecture.py::test_the_runtime_dependencies_are_exactly_pydantic | the one-dependency rule is enforced by a test; no maintenance or update policy |
| AI | Operational overhead | 4 | 5 | 5 | bench (AgentOS ops on scratch DB) | unchanged since re-grade 1; op latency measured, not per-command overhead; no guard |
| AI | Incremental extensibility | 5 | 5 | 5 | see A Extensibility | unchanged since re-grade 1; no plugin API |
| AJ | Provider usage restrictions | 4 | 4 | 7 | unit/test_architecture.py::test_nothing_in_agentos_opens_a_network_connection | AgentOS imports no network module (tested, statically); `evidence run` subprocesses and dynamic imports are not covered; model sessions run only in opt-in live tests |
| AJ | Authorization | 9 | 9 | 9 | see G |  |
| AJ | Data handling | 5 | 7 | 7 | as AC Privacy | unchanged since re-grade 1; as AC Privacy |
| AJ | External action boundaries | 4 | 4 | 4 | by inspection | unchanged since re-grade 1; `evidence run` executes arbitrary commands; no test |
| AJ | License compliance | 4 | 4 | 4 | LICENSE | unchanged since re-grade 1; no license scan |
| AK | Backups | 8 | 8 | 8 | see Y Backup | unchanged since re-grade 1; no failure test |
| AK | Restoration | 9 | 10 | 10 | see Y Restoration |  |
| AK | Interrupted tasks | 6 | 7 | 7 | unit/test_health.py (stale/reap tests) | heartbeats can now come from the hook (guard-tools only); stale detection still runs only on demand |
| AK | Recovery testing | 9 | 9 | 9 | resilience/test_resilience.py::test_backup_restores_real_work_and_keeps_a_safety_copy |  |
| AK | Recovery documentation | 5 | 8 | 8 | docs/RUNBOOK.md:16-24; unit/test_skill_commands.py::test_skill_command_parses; unit/test_architecture.py::test_a_failed_migration_leaves_the_earlier_ones_applied | migration wording fixed and backed by a test; no procedure is executed end to end by a test |
| AL | CLI usability | 7 | 7 | 7 | unit/test_skill_commands.py | unchanged since re-grade 1; no typo suggestions |
| AL | Configuration validation | 9 | 9 | 9 | unit/test_governor.py::test_unknown_limit_rejected |  |
| AL | Examples | 6 | 7 | 7 | docs/EXAMPLES.md; unit/test_skill_commands.py::test_the_guides_show_commands | unchanged since re-grade 1; examples parse but are never executed |
| AL | Debugging | 5 | 7 | 7 | docs/TROUBLESHOOTING.md; unit/test_ops.py::test_timeline_counts_each_day_and_spans_follow_each_worker | unchanged since re-grade 1; spans, timeline, incidents and policy history exist; no verbose/trace mode; spans are worker-level |
| AL | Troubleshooting | 6 | 7 | 8 | docs/REASONS.md; unit/test_ops.py::test_committed_reason_reference_matches_the_source, ::test_the_reason_scan_finds_every_kind_of_refusal; docs/TROUBLESHOOTING.md:17 | all 100 reasons listed, generated and tested for freshness and coverage; remedies for 13 only; doctor prints no fix hints |
| AM | Alternative comparison | 2 | 6 | 6 | unit/test_ops.py::test_options_compare_alternatives_and_admit_uncertainty | unchanged since re-grade 1; worker templates compared side by side; strategic alternatives are not recorded with any decision |
| AM | Uncertainty handling | 1 | 6 | 7 | unit/test_ops.py::test_options_recommend_only_with_enough_history_on_both_sides, ::test_identical_grades_still_get_an_interval | Student t interval with a minimum half-width; `recommend` needs 3+ evaluations of both leading options (n=2 case tested); uncertainty only in `intel options`; docs/LIMITATIONS.md:145 still says normal-approximation |
| AM | Risk analysis | 2 | 5 | 5 | unit/test_ops.py::test_options_compare_alternatives_and_admit_uncertainty | unchanged since re-grade 1; fixed per-option risk list; only `no_history` is asserted; no risk register |
| AM | Cost-benefit evaluation | 1 | 5 | 5 | unit/test_ops.py::test_options_compare_alternatives_and_admit_uncertainty | unchanged since re-grade 1; relative cost units; one arithmetic assertion; not recorded |
| AM | Decision traceability | 5 | 5 | 5 | unit/test_handover.py::test_create_and_resume_cross_host | unchanged since re-grade 1; no decision record type |
| AN | Project activation | 9 | 9 | 9 | unit/test_projects.py |  |
| AN | Memory isolation | 9 | 9 | 9 | security/test_memory_isolation.py |  |
| AN | Project budgets | 8 | 8 | 8 | unit/test_governor.py::test_budget_exceeded_and_release | unchanged since re-grade 1; host-reported usage |
| AN | Cross-project coordination | 5 | 5 | 5 | unit/test_tasks.py::test_cross_project_dependency_denied | unchanged since re-grade 1; no shared work items |
| AN | Project-specific governance | 4 | 8 | 8 | unit/test_ops.py::test_a_project_limit_only_tightens_and_loosening_it_needs_the_owner, ::test_admission_enforces_the_project_slot_limit | unchanged since re-grade 1; per-project limits tighten only, loosening needs the owner; only max_concurrent enforcement is tested (max_depth / agents_per_task via get_limits untested); no per-project policies beyond limits; not in LIMITATIONS |
| AO | Dependency provenance | 5 | 6 | 7 | unit/test_architecture.py::test_every_locked_dependency_is_pinned_with_hashes | every pin carries sha256 hashes and every declared dependency is locked (tested); provenance is PyPI hashes only, with no attestation check; the CI audit has never run |
| AO | Version pinning | 5 | 6 | 8 | unit/test_architecture.py::test_every_locked_dependency_is_pinned_with_hashes; scripts/install.ps1:49-55; integration/test_install_script.py::test_install_then_uninstall | the installer and CI install the exact lock with --require-hashes (installer path exercised by the regression); no refusal case for a drifted or unhashed pin |
| AO | Release reproducibility | 0 | 4 | 4 | .github/workflows/ci.yml reproducible-build job | unchanged since re-grade 1; job written but never run (ci.yml is uncommitted); no test in tests/; the grader could not rebuild offline; the wheel lacks definitions/ |
| AO | Update safety | 7 | 7 | 7 | unit/test_gen.py::test_generator_preserves_human_edits | unchanged since re-grade 1; no package update path |
| AO | Rollback verification | 5 | 5 | 5 | integration/test_cli_system.py::test_backup_then_restore_roundtrip | unchanged since re-grade 1; no release rollback |

## Counts per score

| Score | Baseline | Re-grade 1 | Re-grade 2 |
| --- | --- | --- | --- |
| 10 | 1 | 3 | 3 |
| 9 | 38 | 35 | 36 |
| 8 | 56 | 68 | 79 |
| 7 | 21 | 39 | 42 |
| 6 | 22 | 29 | 22 |
| 5 | 39 | 26 | 24 |
| 4 | 14 | 10 | 4 |
| 3 | 2 | 2 | 2 |
| 2 | 4 | 0 | 0 |
| 1 | 7 | 1 | 1 |
| 0 | 9 | 0 | 0 |
| **>= 9** | **39** | **38** | **39** |

Re-grade 2 against re-grade 1: raised 27, lowered 0, unchanged 186. Rows below 9: 174. Rows whose reason says BLOCKED: 11 (B Delegation, B Coordination, E Recursive delegation, F Safe cancellation, G Policy enforcement, N Codex compatibility, N Skills compatibility, N Hooks and plugin support, Q Live host follows the skill, W Communication, X Compatibility verification).

## Every row below 9, grouped

### (a) fixable in code, tests or docs: 132 rows

- AJ External action boundaries (4): fix: command allowlist with refusal tests
- AJ License compliance (4): fix: license scan of the lock in CI
- AO Release reproducibility (4): fix: commit, run the job, and add definitions/ as package data
- Z No fabricated quality scores (4): fix: publish the scores file and a test that every row cites an existing test
- A Extensibility (5): fix: document an entry-point plugin API and test loading a good and a malformed external plugin
- AA Improvement over baseline (5): fix: measure a promoted change on real work
- AA Reproducibility (5): fix: measure repeat-run variance of trials
- AE Technical debt (5): fix: tracked debt list with owners
- AG Existing framework integration (5): fix: CI test that connects a reference MCP client library and lists/calls tools
- AH Resistance to manipulation (5): fix: Sybil limit: evaluators must have been admitted for a task in the project, capped per task
- AI Incremental extensibility (5): fix: plugin API
- AI Long-term maintenance (5): fix: documented policy and automated dependency updates
- AI Operational overhead (5): fix: time each CLI command in a test and guard a ceiling
- AM Decision traceability (5): fix: a decision record linked to evidence and audit events
- AN Cross-project coordination (5): fix: shared cross-project work items, tested
- AO Rollback verification (5): fix: release rollback test
- C Organizational adaptability (5): fix: track adopted-change outcomes per objective over time
- D Recruitment efficiency (5): fix: bench the recruit path and keep a regression guard
- P Performance trends (5): fix: per-template grade trend (rolling mean) with a planted decline test
- Y Updates (5): fix: `agentos update` with a test that upgrades an installed older version
- A Configuration design (6): fix: add `agentos settings show/set` with a schema, and a CLI test of `health breaker` including the owner refusal
- AA Learning transfer (6): fix: test a shared org lesson used in a second project
- AD Scaling efficiency (6): fix: measure at several ledger sizes (1k/10k/100k events) and assert slowdown below a bound
- AH Score calibration (6): fix: fit weights to accepted/rejected outcomes and test the fit
- AI Dependency sustainability (6): fix: a documented dependency policy and an update bot
- D Validation (6): fix: trial gate before first admission, with a failing-trial test
- E Overhead management (6): fix: measure per-task coordination events/time and add a budget with a refusal
- I Organizational effectiveness (6): fix: a per-period effectiveness series (accepted tasks per admitted worker) with tests
- J Scheduling (6): fix: enforce ready-order in admission, tested
- P Latency (6): fix: aggregate span durations per template/task (p50/p95) and assert planted values
- P Reliability (6): fix: add a per-template reliability series to observe performance and test it
- S Injection resistance (6): fix: taint-mark memory/messages from workers and test the marking
- A Architectural simplicity (7): fix: autouse conftest fixture that makes socket.socket raise for the whole suite, plus a test that no command leaves a background process
- A Modularity (7): fix: extend the AST test with an allowed-imports map per core module and a planted-violation case
- AB Rollback (7): fix: release rollback
- AC Privacy (7): fix: erasure path for evidence tails and handover files, tested
- AD Queue performance (7): fix: run `bench run` in CI against a committed baseline with a tolerance
- AD Resource forecasting (7): fix: validate forecasts against finished objectives
- AE Code quality (7): fix: mypy or pyright in CI
- AE Dependency management (7): fix: an update-bot config plus a freshness test of the scripts/lock_hashes.py output
- AF Installation usability (7): fix: cross-platform installer
- AF Task visibility (7): fix: view tests with empty and error states
- AG Standard schemas (7): fix: validate CLI --json outputs and a refused malformed record against schemas/ in tests
- AJ Data handling (7): fix: as AC Privacy
- AJ Provider usage restrictions (7): fix: a socket-blocking autouse fixture for the suite
- AK Interrupted tasks (7): fix: as H Failure detection
- AL CLI usability (7): fix: suggest close commands on a typo, tested
- AL Debugging (7): fix: `--debug` that prints SQL timing and the audit events a command wrote
- AL Examples (7): fix: run each example block in an integration test
- AO Dependency provenance (7): fix: as S Supply-chain security, plus checking PyPI attestations in CI
- AO Update safety (7): fix: safe package update path, tested
- C Managerial effectiveness (7): fix: add planted ineffective and under-3-evaluation leads, and a per-department roll-up
- D Onboarding (7): fix: put new templates on probation with a failing-probation test
- H Failure detection (7): fix: run a rate-limited `health.reap` from `hook run`, tested, so detection needs no manual step
- H Recovery (7): fix: run reap opportunistically from `hook run` / `agent admit`, tested
- K Memory quality (7): fix: refuse or flag writes below a quality floor (e.g. confidence < 0.2 without source), with a test
- M Availability checks (7): fix: a doctor check that the [models] table exists and parses, with a failing case
- M Capability matching (routing) (7): fix: a `host models` command that writes and validates the table, with a malformed-table refusal test
- M Fallback behavior (7): fix: CLI test of `intel route TASK --host codex` with a profile in AGENTOS_HOME
- O Tracing (7): fix: test a delegated child sharing the root's trace id and an open span; state the worker-level limit
- P Agent quality (7): fix: calibrate weights against outcomes
- S Supply-chain security (7): fix: commit and run CI; add an offline local test (pip --no-index --find-links on a local wheel) that a tampered hash is refused
- V Rollback (7): fix: release rollback path with a test
- V Skill versioning (7): fix: keep a version-to-hash map in plugin.toml and fail when a new hash is paired with a version already listed
- W Conflict resolution (7): fix: detect overlapping edits from evidence git diffs against open claims, tested
- Y Installation (7): fix: cross-platform installer and a tested PATH edit
- Z No fabricated test results (7): fix: parse known test-runner output into pass/fail counts
- A Dependency boundaries (8): fix: add a planted third-party import case and write the one-dependency rule into LIMITATIONS
- A Documentation (8): fix: fix the stale lines, publish PHASE9_SCORES.md, and give every reason a remedy with a test that the column is never empty
- A Separation of concerns (8): fix: add a test that feeds the scanner a planted module importing agentos.cli, and state the clidocs exception in LIMITATIONS
- AA Regression detection (8): fix: calibrate
- AB Versioned proposals (8): fix: conflicting-proposal refusal test
- AC Database consistency (8): fix: test that doctor flags a corrupted DB
- AC Migration (8): fix: as V Migration
- AC Retention (8): fix: add evidence and handover rules and age deleted memory by its deletion event, tested
- AD Load management (8): fix: adaptive load shedding, tested
- AE Documentation (8): fix: fix the stale lines, publish PHASE9_SCORES.md, and give every reason a remedy with a test that the column is never empty
- AE Testability (8): fix: commit and run CI with the gate
- AF Clear error messages (8): fix: make the scanner extract every message (or require a literal message) and test that none is empty
- AF Configuration clarity (8): fix: include every behaviour-changing setting in `policy show`
- AG Adapter architecture (8): fix: verify a third host profile
- AH Benchmark protection (8): fix: normalised/semantic leakage check
- AH Reviewer independence (8): fix: authenticated evaluators
- AK Backups (8): fix: backup failure test
- AK Recovery documentation (8): fix: an integration test that runs the upgrade and broken-chain procedures end to end
- AL Troubleshooting (8): fix: a remedy per reason (test none is empty) and a fix hint per doctor check
- AN Project-specific governance (8): fix: test project max_depth enforcement and add per-project template/risk policy
- AO Version pinning (8): fix: test that the install refuses a lock entry without a hash, and that the lock satisfies the pyproject ranges
- B Escalation (8): fix: skip a new escalation while an unread one exists for the same task (tested), and reap opportunistically from `hook run`
- C Dynamic departments (8): fix: state the threshold limit in LIMITATIONS and the row
- C Role separation (8): fix: per-instance credentials issued at admission, with a spoofed-id refusal test
- D Candidate selection (8): fix: calibrate weights against graded outcomes
- D Capability detection (8): fix: test a near-miss tag and document tag matching in LIMITATIONS
- E Workload adaptation (8): fix: validate effort against finished-task outcomes
- F Knowledge preservation (8): fix: refuse or flag `workforce terminate` with an empty note, with a test
- F Performance diagnosis (8): fix: calibrate against outcomes
- G Independent oversight (8): fix: authenticated evaluator credentials
- H Checkpointing (8): fix: write a checkpoint on each state change, with a test
- H Fault isolation (8): fix: admit a quarantined template and assert `template_unavailable`
- I Capability matching (8): fix: calibrate weights
- J Prioritization (8): fix: test ties, invalid priority refusal
- K Provenance (8): fix: refuse writes without source/author, tested
- K Retrieval (8): fix: synonym expansion or a retrieval benchmark
- K Versioning (8): fix: test history kept and cross-project supersede refused
- L Experimentation (8): fix: require a statistically justified case count
- L Failure analysis (8): fix: retro on a healthy record yields no diagnosis, tested
- L Learning retention (8): fix: count use whenever a context pack is built for an admitted worker, not only with --record
- M Routing evidence (8): fix: state the uncalibrated-threshold limit in the AUDIT row
- N MCP integration (8): fix: check the schema with mcp_server._open_read_only at startup instead of require_initialized, add an MCP entry to LIMITATIONS, and test with a reference MCP client in CI
- O Logging (8): fix: test --kind filter and a bad filter
- O Metrics (8): fix: add value series (tokens charged, mean grade, p50 span duration) and test them
- Q Acceptance criteria (8): fix: add that limit to docs/LIMITATIONS.md
- Q Independent evaluation (8): fix: authenticated evaluators
- R Circuit breakers (8): fix: CLI test of `health breaker` (stricter accepted, milder refused without a terminal) and add `breaker.` to PROTECTED_PREFIXES with a test
- R Error handling (8): fix: fuzz CLI argv and assert no traceback
- R Idempotency (8): fix: idempotency test per mutating command, or a documented list
- S Secret protection (8): fix: entropy-based detection or refuse suspected secrets
- T Capability registry (8): fix: duplicate/invalid capability refusal tests
- T Performance history (8): fix: calibration
- T Succession planning (8): fix: test a balanced org and a no-successor case
- U Context management (8): fix: validate the estimate against a tokenizer sample
- U Duplicate-work prevention (8): fix: near-duplicate task detection, tested
- V Agent versioning (8): fix: stale-version update refusal test
- V Migration (8): fix: seed every table and migrate fixture databases built at each version v1..v7
- V Policy versioning (8): fix: include every non-host setting in the snapshot and add `policy rollback VERSION` (owner), tested
- W Execution graphs (8): fix: track graph completion per objective, tested
- W Workflow reuse (8): fix: add parameters and document the global scope
- X Configuration synchronization (8): fix: resolved-config check through the host CLI
- Y Backup (8): fix: unwritable-destination backup test
- Y Diagnostics (8): fix: more doctor checks each with a failing test
- Y Uninstallation (8): fix: cross-platform uninstall
- Z No fabricated costs (8): fix: test that no path writes a computed cost

### (b) BLOCKED by an external limit: 30 rows

- U Token efficiency (1): limit: hosts do not expose token telemetry
- AI Subscription efficiency (3): limit: hosts expose no subscription usage
- Q Live host follows the skill (3): limit: run `pytest -m session tests/live` with the owner's go-ahead
- N Skills compatibility (5): limit: live skill-follow runs on both hosts (quota)
- P Resource efficiency (5): limit: hosts do not expose real token usage
- AG ECC compatibility (6): limit: live session uses the owner's quota
- F Safe cancellation (6): limit: live Codex check of agent_id on tool calls (quota); hosts expose no kill API
- G Policy enforcement (6): limit: live Codex spawn refusal through the trusted hook
- M Cost-quality balance (6): limit: host cost/usage telemetry is not exposed
- N Hooks and plugin support (6): limit: live Codex spawn through the hook
- X Compatibility verification (6): limit: run tests/live session tests when quota exists
- AG Portable skills (7): limit: live skill-follow runs (quota)
- F Replacement (7): limit: hosts expose no stop API
- N Codex compatibility (7): limit: run `pytest -m session tests/live` when quota exists
- N Second host (`cc`) compatibility (7): limit: live run from the installed plugin uses the owner's model quota (not authorised)
- X Shared learning (7): limit: live sessions on both hosts (quota)
- AN Project budgets (8): limit: runtime usage not exposed by hosts
- B Coordination (8): limit: a live host session following the skill's inbox and claim steps (model quota)
- B Delegation (8): limit: live Codex session refusing an unadmitted child (needs quota)
- E Recursive delegation (8): limit: live Codex hook run refusing a too-deep spawn
- E Workforce contraction (8): limit: hosts expose no stop API to AgentOS
- G Emergency controls (8): limit: needs a live Codex session and a host stop API
- H Reassignment (8): limit: hosts expose no stop API
- O Runtime visibility (8): limit: Codex runtime data needs a live session
- S Permission boundaries (8): limit: a runtime tool-permission gate needs live host hooks
- T Reassignment (8): limit: hosts expose no stop API
- U Cost awareness (8): limit: hosts do not expose real cost data
- U Resource budgets (8): limit: runtime-reported usage not available from hosts
- W Communication (8): limit: a live host session reading and acting on an inbox
- W Parallelism (8): limit: live parallel run needs host sessions

### (c) host-model reasoning by design (still scored honestly): 12 rows

- AM Cost-benefit evaluation (5): what AgentOS could still add: record cost-benefit with the decision; test ordering by value_per_cost
- AM Risk analysis (5): what AgentOS could still add: assert each risk flag with planted data; add a risk record per objective
- B Decision-making (5): what AgentOS could still add: measure schedule adherence or enforce ordering in admission
- I Context understanding (5): what AgentOS could still add: relevance benchmark for the context pack
- I Decision quality (5): what AgentOS could still add: record decision outcomes and compare
- J Task decomposition (5): what AgentOS could still add: decomposition quality checks
- AM Alternative comparison (6): what AgentOS could still add: record the options output with the admission it led to
- B Objective understanding (6): what AgentOS could still add: record objective-to-outcome fidelity (criteria met at delivery) per objective
- B Planning (6): what AgentOS could still add: grade plans against delivery outcomes (re-plans, cancelled tasks)
- I Evidence synthesis (6): what AgentOS could still add: link evidence to claims automatically (e.g. parse test-runner output)
- AM Uncertainty handling (7): what AgentOS could still add: carry the interval into `intel route` and `intel forecast`, and fix LIMITATIONS.md:145
- L Improvement hypotheses (7): what AgentOS could still add: accept host-written hypotheses through the same experiment gate (exists) and measure their win rate

## Status of the 17 defects from re-grade 1

| # | Defect | Status now | How I checked |
| --- | --- | --- | --- |
| 1 | refused claim's `comms.claim_denied` rolled back | FIXED | comms.py:166-186 appends the event inside the transaction and raises after it commits; unit/test_comms.py::test_a_refused_claim_stays_in_the_audit_log passes and asserts the incident |
| 2 | retry-limit escalation invisible to the owner | FIXED | boss.py:488-497 calls comms.escalate_from_agentos in the same transaction; unit/test_health.py::test_a_retry_limit_escalation_reaches_the_owner asserts the dashboard count, the high incident and the chain |
| 3 | `health heartbeat` without project check | FIXED | health.py:29-41 refuses `cross_project`; cli/cmd_ops.py:77 passes the project; unit/test_health.py::test_a_heartbeat_for_another_projects_worker_is_refused |
| 4 | MCP `agentos_route` without project check | FIXED | mcp_server.py:98-102; unit/test_ops.py::test_mcp_route_refuses_another_projects_task |
| 5 | MCP echoes any protocolVersion | FIXED | mcp_server.py:15-16, 119-121; unit/test_ops.py::test_mcp_offers_only_protocol_versions_it_supports |
| 6 | MCP tool calls run migrate() | FIXED for tool calls, NOT for startup | mcp_server.py:64-76 opens with query_only and refuses a pending migration (tested); but `agentos mcp serve` still calls db.require_initialized(), which migrates (new defect N1) |
| 7 | settings.set and breaker outside the policy log | MOSTLY FIXED | policy_log.py:14-16 counts both and the snapshot has the breaker; generic settings are still not in the snapshot (new defect N4) |
| 8 | `models` table undocumented, tested only with None | FIXED | docs/HOST_PROFILE.md:76-90; unit/test_ops.py::test_host_tiers_come_from_the_host_profile_models_table writes a real profile file |
| 9 | normal interval, `recommend` on two grades | FIXED | intel.py:656-714 (t table, MIN_HALF_WIDTH, 3+ on both leading options); unit/test_ops.py::test_options_recommend_only_with_enough_history_on_both_sides |
| 10 | tamper step passes on any pip failure; CI unrun | FIXED IN CODE, UNPROVEN | ci.yml now greps "DO NOT MATCH THE HASHES"; the CI changes are uncommitted and have never run |
| 11 | skill changed without a version bump | FIXED | 0.2.0 in pyproject, __init__, plugin.toml, plugin.json, marketplace.json; skill hash pinned and tested (weakness: see V Skill versioning) |
| 12 | AUDIT.md claimed every reason mapped | FIXED | AUDIT.md:420 now says "common refusal reasons"; docs/REASONS.md lists all 100, generated and freshness-tested |
| 13 | reports/PHASE9_SCORES.md missing | NOT FIXED | still absent; linked from reports/AUDIT.md:19 and README.md:23 |
| 14 | stale coverage figure in AUDIT.md | NOT FIXED, WORSE | reports/AUDIT.md:22-23 still says 830 passed, comms 93%, mcp_server 81%, ops CLI 97%; regression_p9b shows 858, 96%, 84%, 89% |
| 15 | RUNBOOK migration wording | FIXED | docs/RUNBOOK.md:20-22 matches db.py:53-65 and cites the failed-migration test |
| 16 | AUDIT Q Acceptance criteria understated | FIXED | AUDIT.md:203 now cites the delivery-gate tests |
| 17 | workflow tamper hash in the same row | DOCUMENTED | docs/LIMITATIONS.md:136-140 states it catches accidents, not an attacker (code unchanged) |

## New defects (found in this round)

- N1. src/agentos/cli/cmd_ops.py:158: `cmd_mcp_serve` calls `db.require_initialized()`, which runs `db.migrate()` (db.py:85-90), so `agentos mcp serve` applies a pending migration at startup. This contradicts mcp_server.py:64-76 ("a pending migration is refused rather than applied", "this server never writes") and the claim in reports/AUDIT.md:176. The tests exercise only `call_tool` (unit/test_ops.py::test_mcp_refuses_a_pending_migration_instead_of_applying_it), not the CLI entry point.
- N2. src/agentos/boss.py:488-497: every call of `boss recover` on a task at its retry limit sends a new owner escalation; nothing checks for an unread escalation already open for that task, so repeating the command piles up duplicates on the dashboard. (`health reap` does not repeat it, because the task is then `failed`, not `running`.)
- N3. src/agentos/governance.py:16: `breaker.` is not in PROTECTED_PREFIXES, so `governance.set_setting(conn, "breaker.floor", 0, actor)` loosens the circuit breaker without the owner, bypassing the rule in health.set_breaker (health.py:101-124). No CLI exposes set_setting today, so this is a latent library-level bypass.
- N4. src/agentos/policy_log.py:4 and :31: the docstring says the policy includes "other owner-set settings" and CHANGE_KINDS now counts `settings.set`, but `snapshot()` leaves generic settings out of the hashed body. A `settings.set` therefore raises the policy version while the hash stays the same, so two machines can report one hash under different settings.
- N5. src/agentos/cli/cmd_ops.py:82-90: the `health breaker` handler re-implements the "milder" test (also in health.py:115) and is executed by no test (coverage of cli/cmd_ops.py: lines 82-90 missed). My probe shows it behaves correctly today; nothing keeps the two copies in step.
- N6. docs/LIMITATIONS.md:145: says `intel options` uses normal-approximation intervals; the code now uses a Student t interval with a minimum half-width (intel.py:656-668).
- N7. docs/LIMITATIONS.md:186-187: says CI runs the suite on Windows and Ubuntu "and passes there"; the CI file was changed this round (--require-hashes install, coverage gate, tamper check, reproducible build) and that version has never run.
- N8. src/agentos/cli/cmd_ops.py:51: the `retention` group help still says "remove read messages, old benchmark runs and deleted memory", omitting released claims, which retention now removes (retention.py:19-24). Minor.
- N9. docs/REASONS.md: 25 of the 100 rows have an empty message column (for example `capability_mismatch`, `duplicate`, `criteria_without_evidence`) and 87 have no remedy; test_the_reason_scan_finds_every_kind_of_refusal does not check either.
- N10. Carried, not new but still open: src/agentos/retention.py:22 ages a deleted memory record by `created_at`, not by when it was deleted, so a record deleted yesterday but created 100 days ago is removed at once by `retention apply --days 90`.
- N11. docs/LIMITATIONS.md has no MCP entry: the server has never been connected from a real MCP client, and that limit is written nowhere (grep for "MCP" in LIMITATIONS.md finds nothing).

## Top 15 fixable gaps (largest effect on the score table first)

1. Z No fabricated quality scores (4): publish reports/PHASE9_SCORES.md (this table) and add a test that every row cites a test that exists.
2. AO Release reproducibility (4): commit, run the reproducible-build job, and ship `definitions/` as package data so the wheel works without a checkout.
3. AJ External action boundaries (4): an allowlist (or owner confirmation) for `evidence run` commands, with a refusal test.
4. AJ License compliance (4): a license scan of requirements-lock.txt in CI and a test that every locked package has an allowed license.
5. Y Updates (5): an `agentos update` command and a test that upgrades an installed older version with data.
6. A Configuration design (6): `agentos settings show/set` with a schema, routed through governance and the policy log; protect `breaker.` (N3).
7. N MCP integration (8): open the ledger read-only at `mcp serve` startup (N1), add the MCP limit to LIMITATIONS (N11), and connect a reference MCP client in CI.
8. R Circuit breakers (8): a CLI test of `health breaker` (N5) and `breaker.` in PROTECTED_PREFIXES with a test (N3).
9. H Failure detection / H Recovery / AK Interrupted tasks (7): run a rate-limited `health.reap` from `hook run`, so detection and recovery need no manual command.
10. S Supply-chain security (7) / AO Dependency provenance (7): commit and run CI, and add an offline local test (`pip --no-index --find-links` on a local wheel) that a tampered hash is refused.
11. V Skill versioning (7): keep a version-to-hash map in plugin.toml and fail when a new skill hash is paired with an old version.
12. V Migration / AC Migration (8): fixture databases built at every version v1..v7 with rows in every table, each migrated to v8.
13. A Documentation / AE Documentation (8): fix N6, N7, the stale AUDIT.md:22-23 counts and the missing scores file; give every reason a message and a remedy, tested.
14. A Architectural simplicity (7) / AJ Provider usage restrictions (7): an autouse fixture that makes `socket.socket` raise for the whole suite.
15. B Escalation (8): de-duplicate open escalations per task (N2) and test it.
