# V4.0 Phase 9: criterion-by-criterion scores

Every one of the 213 criteria from the 41 original V4.0 audit domains, scored 0 to 10 against the rubric in
[AUDIT_CRITERIA.md](AUDIT_CRITERIA.md), which was written before any grading. Five columns:

- **Baseline**: before the Phase 9 fixes ([PHASE9_BASELINE.md](PHASE9_BASELINE.md)).
- **Re-grade 1** to **Re-grade 4**: after each round of fixes.

Each grade was given by a separate, independent grader that did not write the code, could not edit the
repository, verified each claimed fix in the code and tests, and ran the full suite itself. Scores are never
averaged. A BLOCKED row is not a pass.

**Result: 56 of 213 criteria are at 9 or above** (39 at the baseline). 157 are below 9:

- 115 could be fixed in code, tests or docs (each with its concrete gap below).
- 30 are blocked by an external limit: there is no live Codex session (no model quota), and hosts expose
  no stop API and no token, cost or usage data. Each BLOCKED row names its limit.
- 12 measure the host model's own reasoning, which AgentOS records but does not do.

The goal of 9 or more on every criterion was **not reached**. The rubric gives 9 only to complete work with
a refusal test and a stated limit, so the BLOCKED rows cannot reach it without a live host session, and many
rows at 8 need more negative tests, a CI run of these changes, or capabilities AgentOS does not have.

## What the fourth grader saw

The full suite, run by the grader: 969 passed, 3 deselected (the live tests), 96.22% branch coverage, the 90%
gate met; lint clean. Probes in fresh AgentOS homes covered the automatic stale-worker check, `evidence run`
through the CLI, the outside-command check, memory corrections, the licence rule and `doctor` on a damaged
database. Not run: live host sessions (no Codex quota), CI on these uncommitted changes, a wheel build, a
real MCP client. CI run 45926054163 on commit `6097cb6` (the round before) passed all six jobs: lint and
tests on Windows and Ubuntu with Python 3.11 and 3.12, the dependency audit with the tampered-lock check, and
the reproducible build.

## After re-grade 4

The fourth grader found five new defects (G1 to G5 below). They were fixed after it ran, with tests, but
**they have not been re-graded**, so the scores below do not count them:

| Defect | Fix | Test |
| --- | --- | --- |
| G1 the "readable database" doctor test reached the unreadable branch | renamed for what it does; a new test builds a database that opens but whose index disagrees with its table, and `doctor` reports what `integrity_check` finds | `unit/test_hardening.py::test_doctor_reports_what_integrity_check_finds_in_a_readable_database` |
| G2 the licence rule passed "Proprietary AND MIT"; a version mismatch was skipped | every named licence must be allowed; the installed version must equal the locked one or the test fails | `unit/test_release_hygiene.py::test_the_licence_rule_refuses_copyleft_proprietary_and_unknown_licences` |
| G3 package runners and other installers passed the outside-command check | `npx`, `uvx`, `pipx` count as outside commands; poetry, conda, winget, choco, scoop, brew, apt, go, gem, dotnet installs and `git ls-remote` are listed; `pip3.12` is pip; the remaining misses are stated in `docs/LIMITATIONS.md` | `unit/test_hardening.py::test_external_commands_are_recognised` |
| G4 the remedy was printed in text mode only | the `--json` error body carries `remedies` | `unit/test_hardening.py::test_the_json_refusal_carries_the_remedy` |
| G5 stale counts in the reports | this file rebuilt from re-grade 4; `reports/AUDIT.md` no longer hard-codes the reason count | `unit/test_release_hygiene.py::test_every_test_the_other_reports_cite_exists` |

## 2. Scores

| Domain | Criterion | Baseline | Re-grade 1 | Re-grade 2 | Re-grade 3 | Re-grade 4 | Evidence | Reason if below 9 (or BLOCKED + exact limitation) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | Modularity | 6 | 6 | 7 | 7 | 7 | unit/test_architecture.py::test_the_core_never_imports_the_cli, ::test_the_structural_checks_catch_a_planted_violation | unchanged since re-grade 3; the core-never-imports-the-CLI boundary is enforced and the scanner is shown catching a planted `agentos.cli` import; boundaries between core modules are still not checked |
| A | Extensibility | 5 | 5 | 5 | 5 | 5 | unit/test_gen.py::test_host_generate_uses_profile | unchanged since re-grade 3; no third-party plugin API |
| A | Separation of concerns | 4 | 4 | 8 | 8 | 9 | unit/test_architecture.py::test_the_core_never_imports_the_cli, ::test_the_structural_checks_catch_a_planted_violation; stated limit: the one exception (gen/clidocs.py) and the unchecked boundaries between core modules are now in docs/LIMITATIONS.md (Smaller stated limits, Layering) |  |
| A | Dependency boundaries | 4 | 4 | 8 | 8 | 9 | unit/test_architecture.py::test_the_runtime_dependencies_are_exactly_pydantic, ::test_the_structural_checks_catch_a_planted_violation (a planted `yaml` import is caught); stated limit: the stdlib-plus-pydantic rule is written, and a second dependency needs the rule changed on purpose (docs/LIMITATIONS.md, Layering) |  |
| A | Architectural simplicity | 4 | 4 | 7 | 8 | 8 | tests/conftest.py no_network fixture; unit/test_architecture.py::test_a_network_connection_in_a_test_is_refused, ::test_nothing_in_agentos_opens_a_network_connection | unchanged since re-grade 3; every test now fails on an in-process connection (autouse fixture, refusal tested); subprocesses (`evidence run`, the installer) are not covered and 'no background process' is untested |
| A | Configuration design | 5 | 5 | 6 | 7 | 7 | integration/test_cli_coord_ops.py::test_the_breaker_command_tightens_freely_and_asks_the_owner_to_loosen, ::test_the_breaker_command_refuses_to_loosen_without_the_owner; unit/test_hardening.py::test_doctor_checks_the_host_models_tables | unchanged since re-grade 3; the breaker CLI is now tested both ways (N5) and doctor validates host [models] tables; still no config file and no validated `settings show/set` command |
| A | Documentation | 5 | 8 | 8 | 8 | 8 | unit/test_ops.py::test_every_reason_has_a_remedy_and_a_meaning_and_none_is_stale, ::test_committed_reason_reference_matches_the_source; unit/test_release_hygiene.py::test_every_test_the_other_reports_cite_exists; docs/LIMITATIONS.md | D4 fixed (the retention text now matches retention.py) and LIMITATIONS now has entries for `evidence run` and the automatic reap; the AUDIT external-action row is now true (D2 fixed); still no Python API reference, and stale text remains: reports/PHASE9_SCORES.md:45 says the CI run passed seven jobs (it had six), and the file stops at re-grade 2 and says N9 is not fixed; reports/AUDIT.md:360 and :422 say 100 reasons (102); reports/AUDIT.md:402 overclaims the licence check (G2) |
| B | Objective understanding | 6 | 6 | 6 | 6 | 6 | unit/test_boss.py::test_objective_needs_acceptance_criteria | host-model reasoning (AgentOS records, the host decides): unchanged since re-grade 3; understanding is never measured |
| B | Planning | 6 | 6 | 6 | 6 | 6 | unit/test_boss.py::test_plan_is_all_or_nothing, ::test_plan_validation | host-model reasoning (AgentOS records, the host decides): unchanged since re-grade 3; plan quality unmeasured; heuristics uncalibrated |
| B | Decision-making | 5 | 5 | 5 | 5 | 5 | unit/test_boss.py::test_schedule_puts_the_critical_path_first | host-model reasoning (AgentOS records, the host decides): unchanged since re-grade 3; schedule is advice only |
| B | Delegation | 8 | 8 | 8 | 8 | 8 | unit/test_admission.py::test_depth_and_delegation | unchanged since re-grade 3; BLOCKED: no live Codex spawn through the hook (no Codex model quota) |
| B | Coordination | 5 | 8 | 8 | 8 | 8 | unit/test_comms.py::test_a_refused_claim_stays_in_the_audit_log, ::test_a_claim_is_exclusive_across_overlapping_paths; integration/test_cli_coord_ops.py::test_messages_claims_and_escalations | unchanged since re-grade 3; claim_denied defect fixed (committed before the refusal, shown in incidents, tested); proof local only; BLOCKED: no live worker has read an inbox or taken a claim (live skill-follow needs model quota) |
| B | Accountability | 9 | 9 | 9 | 9 | 9 | unit/test_lifecycle.py::test_illegal_transition_audited |  |
| B | Escalation | 5 | 7 | 8 | 8 | 9 | unit/test_health.py::test_asking_again_at_the_retry_limit_does_not_pile_up_escalations, ::test_a_retry_limit_escalation_reaches_the_owner; unit/test_hardening.py::test_the_hook_reaps_stale_workers_at_most_every_five_minutes, ::test_the_hook_never_fails_a_worker_it_never_heard_from; grader probe (a worker never heard from, 3 hours busy, stayed RUNNING); stated limit: the owner sees an escalation only by running the dashboard (docs/LIMITATIONS.md, Visibility is a command line) |  |
| C | Clear authority | 9 | 9 | 9 | 9 | 9 | unit/test_governance.py::test_cannot_forge_confirmation |  |
| C | Role separation | 8 | 8 | 8 | 8 | 8 | unit/test_performance.py::test_self_eval_rejected | unchanged since re-grade 3; evaluator identity unauthenticated |
| C | Dynamic departments | 8 | 8 | 8 | 8 | 9 | unit/test_boss.py::test_departments_only_when_the_work_justifies_one (one security task gets no department); stated limit: fixed advisory thresholds (docs/LIMITATIONS.md, Smaller stated limits, Departments) |  |
| C | Managerial effectiveness | 0 | 7 | 7 | 7 | 7 | unit/test_ops.py::test_managers_are_judged_by_their_teams_graded_results | unchanged since re-grade 3; built (intel managers); test covers only the `effective` verdict, not `ineffective`/`unrated`; departments are not measured; no refusal case |
| C | Organizational adaptability | 5 | 5 | 5 | 5 | 5 | unit/test_improve.py::test_a_better_policy_is_promoted_then_monitored | unchanged since re-grade 3; not measured across real objectives |
| D | Capability detection | 8 | 8 | 8 | 8 | 8 | unit/test_recruit.py::test_gap_reported | unchanged since re-grade 3; no near-miss capability test |
| D | Candidate selection | 8 | 8 | 8 | 8 | 8 | unit/test_recruit.py::test_rank_prefers_match | unchanged since re-grade 3; weights uncalibrated |
| D | Onboarding | 7 | 7 | 7 | 7 | 7 | unit/test_factory.py::test_register_adds_an_active_template | unchanged since re-grade 3; no probation for brand-new templates |
| D | Validation | 6 | 6 | 6 | 6 | 6 | unit/test_factory.py::test_unsafe_configurations_are_refused | unchanged since re-grade 3; no behavioural trial before first use |
| D | Recruitment efficiency | 5 | 5 | 5 | 5 | 5 | unit/test_factory.py::test_recruit_uses_an_existing_template_when_one_fits | unchanged since re-grade 3; efficiency not measured |
| E | Recursive delegation | 8 | 8 | 8 | 8 | 8 | unit/test_admission.py::test_depth_and_delegation | unchanged since re-grade 3; BLOCKED: live gate proven on `cc` only; Codex needs quota |
| E | Concurrency | 9 | 9 | 9 | 9 | 9 | concurrency/test_parallel_admission.py::test_parallel_processes_never_exceed_limit |  |
| E | Workload adaptation | 8 | 8 | 8 | 8 | 8 | unit/test_workforce.py::test_split_by_workload | unchanged since re-grade 3; effort figures are host estimates |
| E | Overhead management | 6 | 6 | 6 | 6 | 6 | unit/test_admission.py::test_max_agents_per_task | unchanged since re-grade 3; bench measures AgentOS ops, not coordination overhead |
| E | Workforce contraction | 8 | 8 | 8 | 8 | 8 | unit/test_workforce.py::test_contract_archives_dissolves_and_expires | unchanged since re-grade 3; running native workers are reported, not stopped; BLOCKED: hosts expose no stop API to AgentOS |
| F | Performance diagnosis | 8 | 8 | 8 | 8 | 8 | unit/test_performance.py::test_bands_and_retain | unchanged since re-grade 3; weights uncalibrated |
| F | Rehabilitation | 9 | 9 | 9 | 9 | 9 | unit/test_workforce.py::test_rehabilitation_cannot_widen_permissions |  |
| F | Suspension | 9 | 9 | 9 | 9 | 9 | unit/test_workforce.py::test_review_suspends_after_failing_in_a_row; unit/test_health.py::test_the_breaker_suspends_a_template_after_repeated_failures |  |
| F | Safe cancellation | 6 | 6 | 6 | 6 | 6 | unit/test_lifecycle.py::test_terminate_unconfirmed_is_recorded | unchanged since re-grade 3; BLOCKED: guard-tools needs agent_id on Codex tool calls, unverified without a live session; no native kill |
| F | Replacement | 7 | 7 | 7 | 7 | 7 | unit/test_workforce.py::test_refused_transfer_leaves_the_old_worker_running | unchanged since re-grade 3; old native worker stopped by hand; BLOCKED: hosts expose no stop API |
| F | Knowledge preservation | 8 | 8 | 8 | 8 | 9 | unit/test_workforce.py::test_terminate_failed_worker_records_a_failure_lesson; unit/test_hardening.py::test_terminating_without_a_note_says_the_knowledge_was_not_kept, ::test_the_cli_warns_when_a_worker_is_terminated_without_a_note; stated limit: the note is the host's to write, and a worker failed by the automatic check leaves none (docs/LIMITATIONS.md, The automatic stale-worker check) |  |
| G | Owner authority | 9 | 9 | 9 | 9 | 9 | unit/test_governor.py::test_raise_limit_needs_owner |  |
| G | Approval requirements | 9 | 9 | 9 | 9 | 9 | unit/test_governance.py::test_approval_single_use |  |
| G | Policy enforcement | 6 | 6 | 6 | 6 | 6 | unit/test_runtime.py::test_spawn_without_a_ticket_is_denied | unchanged since re-grade 3; BLOCKED: no live Codex spawn refusal (quota); hosts without hooks only cooperate |
| G | Emergency controls | 8 | 8 | 8 | 8 | 8 | integration/test_cli_flows.py::test_emergency_stop_blocks_admission_and_lift_needs_owner | unchanged since re-grade 3; running workers cannot be halted; guard-tools unverified on Codex; BLOCKED: needs a live Codex session and a host stop API |
| G | Independent oversight | 8 | 8 | 8 | 8 | 8 | unit/test_intel.py::test_governance_catches_each_planted_violation | unchanged since re-grade 3; evaluator identity unauthenticated |
| H | Failure detection | 5 | 7 | 7 | 7 | 8 | unit/test_hardening.py::test_the_hook_reaps_stale_workers_at_most_every_five_minutes, ::test_the_hook_never_fails_a_worker_it_never_heard_from, ::test_a_worker_heard_from_within_the_hour_is_left_alone, ::test_start_and_stop_events_do_not_run_the_check; unit/test_health.py (stale and heartbeat tests); grader probes | D1 fixed: the automatic check fails only workers that were heard from and then silent for an hour, and runs on tool calls only (probe: a worker never heard from, 3 hours busy, stayed RUNNING through its own SubagentStop and another spawn; a worker heard from and then silent 61 minutes was failed and its task reset to pending); limit in LIMITATIONS; but the default hook config records no heartbeat, so a crashed worker is found automatically only with `hook config --guard-tools` or a host that runs `health heartbeat`, and agent_id on Codex tool calls is unverified (live session needs quota) |
| H | Recovery | 6 | 7 | 7 | 7 | 8 | unit/test_health.py::test_reap_fails_a_silent_worker_frees_its_slot_and_retries_its_task, ::test_reap_leaves_live_workers_alone; unit/test_hardening.py::test_the_hook_reaps_stale_workers_at_most_every_five_minutes, ::test_the_hook_never_fails_a_worker_it_never_heard_from; grader probe | the false recoveries of D1 are gone (a worker never heard from is left alone; tested and probed); automatic recovery covers only workers that reported before, which the default hook config never makes happen; the host starts the retry |
| H | Checkpointing | 8 | 8 | 8 | 8 | 8 | unit/test_handover.py::test_create_and_resume_cross_host | unchanged since re-grade 3; no automatic checkpoints |
| H | Reassignment | 8 | 8 | 8 | 8 | 8 | unit/test_workforce.py::test_transfer_picks_a_replacement_and_briefs_it | unchanged since re-grade 3; host must stop the old native worker; BLOCKED: hosts expose no stop API |
| H | Fault isolation | 8 | 8 | 8 | 8 | 8 | unit/test_performance.py::test_security_flag_quarantines | unchanged since re-grade 3; no direct quarantined-template admission test |
| I | Decision quality | 5 | 5 | 5 | 5 | 5 | unit/test_intel.py::test_compete_picks_the_independent_winner_and_disqualifies_the_rest | host-model reasoning (AgentOS records, the host decides): unchanged since re-grade 3; host makes the decisions; outcomes unmeasured |
| I | Context understanding | 5 | 5 | 5 | 5 | 5 | unit/test_intel.py::test_context_pack_puts_validated_and_failures_first_and_respects_the_budget | host-model reasoning (AgentOS records, the host decides): unchanged since re-grade 3; understanding unmeasured |
| I | Capability matching | 8 | 8 | 8 | 8 | 8 | unit/test_recruit.py::test_rank_prefers_match | unchanged since re-grade 3; weights uncalibrated |
| I | Evidence synthesis | 6 | 6 | 6 | 6 | 6 | security/test_phase1_defects.py::test_d06_free_text_evidence_alone_is_rejected | host-model reasoning (AgentOS records, the host decides): unchanged since re-grade 3; synthesis is the host's |
| I | Organizational effectiveness | 6 | 6 | 6 | 6 | 6 | unit/test_intel.py::test_org_review_finds_idle_overlapping_single_point_overloaded_and_idle_departments | unchanged since re-grade 3; no longitudinal outcome metric |
| J | Task decomposition | 5 | 5 | 5 | 5 | 5 | unit/test_tasks.py::test_depth_limit | host-model reasoning (AgentOS records, the host decides): unchanged since re-grade 3; the host decomposes |
| J | Dependency management | 10 | 10 | 10 | 10 | 10 | unit/test_tasks.py::test_cycle_rejected, ::test_cross_project_dependency_denied |  |
| J | Scheduling | 6 | 6 | 6 | 6 | 6 | unit/test_tasks.py::test_ready_orders_by_priority | unchanged since re-grade 3; no enforcing scheduler |
| J | Prioritization | 8 | 8 | 8 | 8 | 8 | unit/test_tasks.py::test_ready_orders_by_priority | unchanged since re-grade 3; happy path only |
| J | Execution state | 9 | 9 | 9 | 9 | 9 | unit/test_tasks.py::test_illegal_transition |  |
| K | Memory quality | 5 | 7 | 7 | 7 | 7 | unit/test_ops.py::test_memory_quality_and_reuse_follow_what_is_validated_and_used | unchanged since re-grade 3; scoring and prune candidates tested; low-quality writes are never refused; fixed weights |
| K | Provenance | 8 | 8 | 8 | 8 | 9 | unit/test_hardening.py::test_memory_without_its_source_or_author_is_refused, ::test_a_correction_without_its_author_is_refused; integration/test_cli_flows.py::test_memory_cli_round_trip; grader probes (CLI `--source " "` exit 3 no_provenance; memory.correct with an empty or blank author refused); stated limit: source and author are unauthenticated free text (docs/LIMITATIONS.md, Provenance) |  |
| K | Retrieval | 8 | 8 | 8 | 8 | 8 | unit/test_memory.py::test_fts_special_chars_safe | unchanged since re-grade 3; keyword only |
| K | Versioning | 8 | 8 | 8 | 8 | 8 | unit/test_memory.py::test_correct_supersedes | unchanged since re-grade 3; happy path only |
| K | Knowledge transfer | 9 | 9 | 9 | 9 | 9 | security/test_memory_isolation.py::test_org_visible_across_projects_only_when_validated |  |
| L | Feedback capture | 9 | 9 | 9 | 9 | 9 | unit/test_performance.py::test_every_score_is_required |  |
| L | Failure analysis | 8 | 8 | 8 | 8 | 8 | unit/test_improve.py::test_retro_diagnoses_weaknesses_and_proposes_a_testable_change | unchanged since re-grade 3; no healthy-record negative retro test |
| L | Improvement hypotheses | 7 | 7 | 7 | 7 | 7 | unit/test_improve.py::test_recurring_capability_mismatches_suggest_a_recruitment_policy | host-model reasoning (AgentOS records, the host decides): unchanged since re-grade 3; fixed rule-based addenda |
| L | Experimentation | 8 | 8 | 8 | 8 | 8 | unit/test_improve.py::test_a_better_challenger_is_promoted_into_the_champion | unchanged since re-grade 3; small samples |
| L | Learning retention | 5 | 8 | 8 | 8 | 8 | unit/test_ops.py::test_memory_quality_and_reuse_follow_what_is_validated_and_used | unchanged since re-grade 3; reuse rate built and tested; counted only when a host asks for `intel context --record` (stated in LIMITATIONS), which no live host has done |
| M | Capability matching (routing) | 6 | 6 | 7 | 8 | 8 | unit/test_ops.py::test_host_tiers_come_from_the_host_profile_models_table; unit/test_hardening.py::test_doctor_checks_the_host_models_tables; docs/HOST_PROFILE.md | unchanged since re-grade 3; tiers map through a documented, tested [models] table and doctor now reports a malformed one (tested); the user writes the table by hand; whether the host used the chosen model is unverified (live session needs Codex quota) |
| M | Cost-quality balance | 6 | 6 | 6 | 6 | 6 | unit/test_intel.py::test_a_strong_record_lowers_medium_risk_but_never_critical | unchanged since re-grade 3; hand-picked thresholds, no real cost data; BLOCKED: host cost/usage telemetry is not exposed |
| M | Availability checks | 4 | 5 | 7 | 8 | 8 | unit/test_ops.py::test_host_tiers_come_from_the_host_profile_models_table, ::test_route_falls_back_to_a_safe_available_tier; unit/test_hardening.py::test_doctor_checks_the_host_models_tables; docs/LIMITATIONS.md (Model availability) | the limit is now written, but it is the heart of the criterion: real model or quota availability is never checked, only the hand-written [models] table |
| M | Fallback behavior | 0 | 6 | 7 | 7 | 7 | unit/test_ops.py::test_route_falls_back_to_a_safe_available_tier, ::test_host_tiers_come_from_the_host_profile_models_table | unchanged since re-grade 3; fallback order and the escalate case tested with a real profile (high risk never falls to a smaller tier); no CLI test of `intel route --host` picking a fallback; the host switches the model |
| M | Routing evidence | 7 | 7 | 8 | 8 | 9 | unit/test_intel.py::test_routing_follows_risk_effort_and_record, ::test_a_weak_record_raises_the_tier (missing-history and no-candidate cases); stated limit: hand-picked, uncalibrated thresholds, now named in the AUDIT row (reports/AUDIT.md:169) and in docs/LIMITATIONS.md (Heuristics are uncalibrated) |  |
| N | Codex compatibility | 7 | 7 | 7 | 7 | 7 | live/test_host_compat.py::test_codex_accepts_the_installed_plugin | unchanged since re-grade 3; BLOCKED: no live Codex session (no model quota) |
| N | Second host (`cc`) compatibility | 7 | 7 | 7 | 7 | 7 | live/test_host_compat.py::test_the_second_host_validates_the_installed_plugin | unchanged since re-grade 3; live gate ran from local settings, not the installed plugin; BLOCKED: live run from the installed plugin uses the owner's model quota (not authorised) |
| N | Skills compatibility | 5 | 5 | 5 | 5 | 5 | unit/test_skill_commands.py | unchanged since re-grade 3; version bump done (0.2.0, skill hash pinned); BLOCKED: no live host followed the skill |
| N | MCP integration | 0 | 7 | 8 | 8 | 8 | unit/test_ops.py MCP tests; integration/test_cli_coord_ops.py::test_mcp_serve_does_not_migrate_the_ledger | unchanged since re-grade 3; N1 fixed (serve no longer opens the ledger at startup; tested) and N11 fixed (LIMITATIONS has an MCP entry); still never connected from a real MCP client: the only client is the project's own test |
| N | Hooks and plugin support | 6 | 6 | 6 | 6 | 6 | integration/test_codex_hook_discovery.py; unit/test_runtime.py | unchanged since re-grade 3; the runtime hook now also records heartbeats (unit/test_runtime.py); BLOCKED: live Codex spawn through the hook not run (quota) |
| O | Logging | 8 | 8 | 8 | 8 | 8 | integration/test_cli_audit.py::test_audit_log_lists_events | unchanged since re-grade 3; filters/error cases untested |
| O | Metrics | 5 | 8 | 8 | 8 | 8 | unit/test_ops.py::test_timeline_counts_each_day_and_spans_follow_each_worker | unchanged since re-grade 3; daily series tested incl. days=0 refusal; series are event counts only (no amounts, durations or scores); command line only |
| O | Tracing | 5 | 7 | 7 | 7 | 7 | unit/test_ops.py::test_timeline_counts_each_day_and_spans_follow_each_worker | unchanged since re-grade 3; one span per worker; test covers a single root span only (no parent/child trace sharing, no open span); no tool-call spans; not in LIMITATIONS |
| O | Auditability | 9 | 9 | 9 | 9 | 9 | unit/test_audit.py::test_tamper_detected |  |
| O | Runtime visibility | 8 | 8 | 8 | 8 | 8 | unit/test_observe.py::test_active_agents_lists_slot_holders_with_what_the_host_reported | unchanged since re-grade 3; not live; Codex runtime data unverified; BLOCKED: Codex runtime data needs a live session |
| P | Agent quality | 7 | 7 | 7 | 7 | 7 | unit/test_performance.py::test_weights_sum_to_one | unchanged since re-grade 3; weights uncalibrated; tests mostly arithmetic |
| P | Reliability | 5 | 6 | 6 | 6 | 6 | unit/test_health.py::test_the_breaker_suspends_a_template_after_repeated_failures; unit/test_performance.py:139 | unchanged since re-grade 3; failure rate drives the breaker; still no dedicated reliability metric (success rate over time per template) with its own test |
| P | Latency | 1 | 6 | 6 | 6 | 6 | unit/test_ops.py::test_bench_measures_without_touching_the_live_ledger_and_flags_a_regression, ::test_timeline_counts_each_day_and_spans_follow_each_worker | unchanged since re-grade 3; bench measures AgentOS's own ops; agent latency exists only as span duration_s, asserted only >= 0; no per-task or per-template latency figures |
| P | Resource efficiency | 5 | 5 | 5 | 5 | 5 | unit/test_governor.py::test_budget_exceeded_and_release | unchanged since re-grade 3; host-reported estimates; BLOCKED: hosts do not expose real token usage |
| P | Performance trends | 1 | 5 | 5 | 5 | 5 | unit/test_ops.py::test_bench_measures_without_touching_the_live_ledger_and_flags_a_regression | unchanged since re-grade 3; trend and regression flag exist only for AgentOS benchmarks; no trend of agent performance (grades over time) |
| Q | Acceptance criteria | 6 | 6 | 8 | 8 | 9 | unit/test_boss.py::test_objective_needs_acceptance_criteria, ::test_delivery_is_gated, ::test_accept_needs_independent_passing_evidence; stated limit: whether evidence meets the criterion's words is the grader's judgement (docs/LIMITATIONS.md, Acceptance criteria) |  |
| Q | Independent evaluation | 8 | 8 | 8 | 8 | 8 | unit/test_performance.py::test_parent_and_child_eval_rejected | unchanged since re-grade 3; identity unauthenticated |
| Q | Testing | 9 | 9 | 9 | 9 | 9 | grader full run: 969 passed, 3 deselected, no skips, 96.22% branch coverage (7230 statements, 181 missed), 90% gate met; ruff clean on src, tests, scripts; CI run 45926054163 on commit 6097cb6 (read by grader 3); stated limit: live tests opt-in, macOS untested (docs/LIMITATIONS.md); the uncommitted round-3 and later changes have not run in CI |  |
| Q | Regression prevention | 9 | 9 | 9 | 9 | 9 | unit/test_ops.py::test_committed_schemas_match_the_models, ::test_committed_cli_reference_matches_the_parser; unit/test_gen.py::test_committed_codex_plugin_is_up_to_date |  |
| Q | Evidence integrity | 9 | 9 | 9 | 9 | 9 | unit/test_performance.py::test_evidence_must_exist_and_belong_to_the_project |  |
| Q | Live host follows the skill | 3 | 3 | 3 | 3 | 3 | live/test_codex_smoke.py::test_codex_follows_skill (not run) | unchanged since re-grade 3; BLOCKED: needs a Codex model session; this account has no quota |
| R | Error handling | 8 | 8 | 8 | 8 | 9 | unit/test_hardening.py::test_database_errors_are_told_apart, ::test_a_file_error_is_exit_2_without_a_traceback, ::test_other_commands_on_a_damaged_database_point_to_doctor, ::test_bad_input_never_ends_in_a_traceback (now requires exit 2 to 5); unit/test_cli_skeleton.py::test_agentos_error_maps_exit_code; coverage in my run: cli/__init__.py 97%, the OSError and database-error branches executed; stated limit: a mistyped option gets argparse's message without a suggestion (docs/LIMITATIONS.md, Error handling; probe `--prioirty`) |  |
| R | Idempotency | 8 | 8 | 8 | 8 | 8 | unit/test_db.py::test_migrate_idempotent | unchanged since re-grade 3; not every mutating command covered |
| R | Circuit breakers | 4 | 8 | 8 | 8 | 9 | integration/test_cli_coord_ops.py::test_the_breaker_command_tightens_freely_and_asks_the_owner_to_loosen, ::test_the_breaker_command_refuses_to_loosen_without_the_owner; unit/test_health.py::test_the_breaker_settings_are_protected_from_the_generic_setter, ::test_the_breaker_suspends_a_template_after_repeated_failures; stated limit: window and floor are untuned defaults (docs/LIMITATIONS.md, Circuit breaker) |  |
| R | State consistency | 9 | 9 | 9 | 9 | 9 | resilience/test_resilience.py::test_an_error_inside_a_transaction_leaves_no_partial_write |  |
| R | Failure recovery | 9 | 9 | 9 | 9 | 9 | resilience/test_resilience.py::test_a_process_killed_mid_write_corrupts_nothing |  |
| S | Permission boundaries | 8 | 8 | 8 | 8 | 8 | security/test_owner_guard.py | unchanged since re-grade 3; agent tool permissions enforced by the host; BLOCKED: a runtime tool-permission gate needs live host hooks |
| S | Isolation | 9 | 8 | 9 | 9 | 9 | security/test_memory_isolation.py; security/test_phase1_defects.py::test_d17_*; unit/test_health.py::test_a_heartbeat_for_another_projects_worker_is_refused; unit/test_ops.py::test_mcp_route_refuses_another_projects_task |  |
| S | Secret protection | 8 | 8 | 8 | 8 | 8 | security/test_redact.py; unit/test_comms.py::test_secrets_in_a_message_are_redacted_before_storage | unchanged since re-grade 3; pattern-based |
| S | Injection resistance | 6 | 6 | 6 | 6 | 6 | unit/test_memory.py::test_fts_special_chars_safe | unchanged since re-grade 3; prompt content reaching hosts untested |
| S | Supply-chain security | 5 | 6 | 7 | 8 | 8 | unit/test_architecture.py::test_every_locked_dependency_is_pinned_with_hashes; unit/test_release_hygiene.py::test_the_hash_check_catches_a_planted_unhashed_pin; integration/test_install_script.py::test_install_then_uninstall; CI run 45926054163 on commit 6097cb6 (read by grader 3) | the static hash check is now shown catching a planted unhashed pin, but the install-time tamper refusal is still proven only in CI, not in tests/; the uncommitted changes have not run in CI; build backend not hash-checked (in LIMITATIONS); no signing |
| T | Capability registry | 8 | 8 | 8 | 8 | 8 | unit/test_templates.py::test_versioning | unchanged since re-grade 3; no registry-specific refusal tests |
| T | Performance history | 8 | 8 | 8 | 8 | 8 | unit/test_performance.py::test_bands_and_retain | unchanged since re-grade 3; uncalibrated |
| T | Promotion | 9 | 9 | 9 | 9 | 9 | unit/test_improve.py::test_a_weaker_challenger_is_rejected_and_remembered |  |
| T | Reassignment | 8 | 8 | 8 | 8 | 8 | unit/test_workforce.py::test_transfer_to_a_named_template | unchanged since re-grade 3; native stop is the host's; BLOCKED: hosts expose no stop API |
| T | Succession planning | 8 | 8 | 8 | 8 | 8 | unit/test_workforce.py::test_succession_finds_successors_and_single_points_of_failure | unchanged since re-grade 3; no negative case |
| U | Token efficiency | 1 | 1 | 1 | 1 | 1 | none | unchanged since re-grade 3; host tokens invisible; BLOCKED: hosts do not expose token telemetry |
| U | Context management | 8 | 8 | 8 | 8 | 8 | unit/test_intel.py::test_context_pack_puts_validated_and_failures_first_and_respects_the_budget | unchanged since re-grade 3; 4-chars-per-token estimate |
| U | Resource budgets | 8 | 8 | 8 | 8 | 8 | unit/test_governor.py::test_budget_exceeded_and_release | unchanged since re-grade 3; host-reported usage; BLOCKED: runtime-reported usage not available from hosts |
| U | Duplicate-work prevention | 8 | 8 | 8 | 8 | 8 | unit/test_admission.py::test_duplicate | unchanged since re-grade 3; exact duplicates only |
| U | Cost awareness | 8 | 8 | 8 | 8 | 8 | unit/test_governor.py::test_paid_spend_blocked | unchanged since re-grade 3; host-reported costs; BLOCKED: hosts do not expose real cost data |
| V | Agent versioning | 8 | 8 | 8 | 8 | 8 | unit/test_templates.py::test_versioning | unchanged since re-grade 3; no version-conflict refusal |
| V | Skill versioning | 4 | 4 | 7 | 7 | 7 | unit/test_architecture.py::test_one_version_everywhere_and_a_changed_skill_needs_a_new_version | unchanged since re-grade 3; skill hash pinned and one version in four files (0.2.0); the test still passes if only skill_sha256 is updated without bumping the version (it checks equality, not that the version moved); no per-skill version |
| V | Policy versioning | 2 | 7 | 8 | 8 | 8 | unit/test_ops.py::test_every_policy_change_raises_the_version_and_changes_the_hash, ::test_the_breaker_is_a_policy_change_and_milder_needs_the_owner | unchanged since re-grade 3; the docstring now says what the hash covers (N4); the behaviour remains: a generic `settings.set` raises the version without changing the hash, so two machines can share a hash under different settings; no rollback |
| V | Migration | 7 | 7 | 8 | 8 | 8 | unit/test_architecture.py::test_a_populated_first_release_database_upgrades_to_the_current_schema, ::test_a_failed_migration_leaves_the_earlier_ones_applied; unit/test_db.py::test_migrate_idempotent; docs/LIMITATIONS.md (Migrations) | the limit is now written, but it is a material part unproven: later migrations that alter populated tables (for example agent_instances) are tested only on empty tables |
| V | Rollback | 7 | 7 | 7 | 7 | 7 | unit/test_adapters.py::test_update_backs_up_and_rollback_restores_exactly | unchanged since re-grade 3; no release rollback |
| W | Execution graphs | 8 | 8 | 8 | 8 | 8 | unit/test_tasks.py::test_cycle_rejected | unchanged since re-grade 3; host executes the graph |
| W | Parallelism | 8 | 8 | 8 | 8 | 8 | concurrency/test_parallel_admission.py | unchanged since re-grade 3; actual parallel execution is the host's; BLOCKED: live parallel run needs host sessions |
| W | Communication | 1 | 8 | 8 | 8 | 8 | unit/test_comms.py::test_messages_reach_the_recipient_and_broadcasts_reach_everyone_else, ::test_bad_messages_are_refused, ::test_secrets_in_a_message_are_redacted_before_storage | unchanged since re-grade 3; mailbox built and tested with refusals and redaction; proof local only: no live worker has read an inbox (live skill-follow BLOCKED) |
| W | Conflict resolution | 1 | 7 | 7 | 7 | 7 | unit/test_comms.py::test_a_claim_is_exclusive_across_overlapping_paths, ::test_a_dead_holder_does_not_block_others | unchanged since re-grade 3; refused claims are now audited (fixed); unclaimed overlapping edits are not detected; resolution is escalation |
| W | Workflow reuse | 2 | 8 | 8 | 8 | 9 | unit/test_workflows.py (7 tests incl. malformed, cycle, not_delivered, tampered); stated limits: the hash catches accidents, not an attacker; workflows are shared by every project and not parameterised (docs/LIMITATIONS.md); none stops a delivered workflow being reused |  |
| X | Handover quality | 9 | 9 | 9 | 9 | 9 | unit/test_handover.py::test_head_advanced_and_diverged |  |
| X | Configuration synchronization | 8 | 8 | 8 | 8 | 8 | unit/test_adapters.py::test_drift_finds_hand_edits_deletions_stale_definitions_and_host_updates | unchanged since re-grade 3; reads files only |
| X | Shared learning | 7 | 7 | 7 | 7 | 7 | integration/test_cli_host.py::test_work_and_learning_cross_hosts_both_ways | unchanged since re-grade 3; no live cross-host run; BLOCKED: live sessions on both hosts (quota) |
| X | Session recovery | 9 | 9 | 9 | 9 | 9 | unit/test_handover.py::test_second_resume_denied |  |
| X | Compatibility verification | 6 | 6 | 6 | 6 | 6 | integration/test_cli_host.py::test_work_and_learning_cross_hosts_both_ways | unchanged since re-grade 3; BLOCKED: live Codex session (no quota) |
| Y | Installation | 7 | 7 | 7 | 7 | 7 | integration/test_install_script.py::test_install_then_uninstall | unchanged since re-grade 3; Windows only; PATH edit untested |
| Y | Updates | 4 | 4 | 5 | 5 | 5 | docs/RUNBOOK.md:16-24; unit/test_architecture.py::test_a_populated_first_release_database_upgrades_to_the_current_schema | unchanged since re-grade 3; the upgrade is new code plus `agentos init`, whose migration is now tested on a populated DB; no update command and no package-upgrade test |
| Y | Diagnostics | 8 | 8 | 8 | 8 | 8 | integration/test_cli_system.py::test_doctor_reports_statuses; unit/test_hardening.py::test_doctor_reports_a_damaged_database_instead_of_crashing, ::test_doctor_reports_damage_inside_a_readable_database, ::test_doctor_checks_the_host_models_tables; grader probe | the limit is now written (docs/LIMITATIONS.md, Diagnostics); but the new 'damage inside a readable database' test reaches the 'cannot be read (database disk image is malformed)' branch (cmd_system.py:66-69), not an integrity_check that runs and reports errors (cmd_system.py:59-61), so that path is still untested (grader probe; G1); no pending-migration check, not stated |
| Y | Backup | 8 | 8 | 8 | 8 | 9 | integration/test_cli_system.py::test_backup_then_restore_roundtrip; unit/test_hardening.py::test_backup_to_an_unwritable_place_is_a_clean_refusal, ::test_a_failed_copy_leaves_no_half_written_backup (db.py:129-132 now executed); stated limit: plain, unencrypted copies on this machine (docs/LIMITATIONS.md, Backups) |  |
| Y | Restoration | 9 | 10 | 10 | 10 | 10 | integration/test_cli_system.py::test_restore_rejects_non_sqlite, ::test_restore_rejects_newer_schema; docs/RUNBOOK.md |  |
| Y | Uninstallation | 8 | 8 | 8 | 8 | 8 | integration/test_install_script.py::test_uninstall_dry_run_changes_nothing | unchanged since re-grade 3; Windows only |
| Z | No fabricated agents | 9 | 9 | 9 | 9 | 9 | unit/test_recruit.py::test_gap_reported |  |
| Z | No fabricated test results | 7 | 7 | 7 | 7 | 7 | security/test_phase1_defects.py::test_d06_* | unchanged since re-grade 3; a command that proves nothing is accepted |
| Z | No fabricated costs | 8 | 8 | 8 | 8 | 8 | unit/test_handover.py (usage_note) | unchanged since re-grade 3; no test that no cost is computed |
| Z | No fabricated performance | 9 | 9 | 9 | 9 | 9 | unit/test_performance.py::test_insufficient_evidence_under_5 |  |
| Z | No fabricated quality scores | 4 | 4 | 4 | 8 | 8 | unit/test_release_hygiene.py::test_every_test_the_audit_cites_exists, ::test_every_test_the_other_reports_cite_exists, ::test_the_citation_check_catches_a_planted_missing_test; reports/PHASE9_SCORES.md | the citation check now covers PHASE9_SCORES.md, PHASE9_DELIVERABLES.md and COMPATIBILITY.md and the limit is written (Scores); but reports/PHASE9_SCORES.md still says things that are false today: the CI run "passed all seven jobs" (six), N9 "not fixed", and it gives the re-grade 2 count as the result with no re-grade 3 column |
| AA | Improvement over baseline | 5 | 5 | 5 | 5 | 5 | unit/test_improve.py::test_a_better_challenger_is_promoted_into_the_champion | unchanged since re-grade 3; no real improvement measured |
| AA | Candidate validation | 9 | 9 | 9 | 9 | 9 | unit/test_improve.py::test_a_failing_gate_blocks_promotion |  |
| AA | Regression detection | 8 | 8 | 8 | 8 | 8 | unit/test_improve.py::test_a_regression_after_promotion_is_rolled_back | unchanged since re-grade 3; window/margin uncalibrated |
| AA | Reproducibility | 5 | 5 | 5 | 5 | 5 | content-hashed cases (unit/test_improve.py) | unchanged since re-grade 3; repeat-run variance unmeasured |
| AA | Learning transfer | 5 | 6 | 6 | 6 | 6 | unit/test_ops.py::test_memory_quality_and_reuse_follow_what_is_validated_and_used | unchanged since re-grade 3; `intel reuse` reports cross_project_lessons_used, but no test creates or asserts a cross-project lesson's use |
| AB | Experiment isolation | 9 | 9 | 9 | 9 | 9 | unit/test_improve.py::test_the_challenger_is_an_isolated_candidate |  |
| AB | Versioned proposals | 8 | 8 | 8 | 8 | 8 | unit/test_improve.py::test_a_regression_after_promotion_is_rolled_back | unchanged since re-grade 3; no conflicting-proposal refusal |
| AB | Staged promotion | 9 | 9 | 9 | 9 | 9 | unit/test_improve.py::test_a_holding_improvement_is_adopted |  |
| AB | No unauthorized self-modification | 9 | 9 | 9 | 9 | 9 | unit/test_policy.py::test_sensitive_or_unknown_names_are_not_tunable |  |
| AB | Protected governance | 9 | 9 | 9 | 9 | 9 | unit/test_governance.py::test_protected_setting_needs_owner |  |
| AB | Rollback | 7 | 7 | 7 | 7 | 7 | see V Rollback | unchanged since re-grade 3; no release rollback |
| AC | Database consistency | 8 | 8 | 8 | 8 | 8 | doctor integrity_check; unit/test_hardening.py::test_doctor_reports_a_damaged_database_instead_of_crashing, ::test_doctor_reports_damage_inside_a_readable_database, ::test_other_commands_on_a_damaged_database_point_to_doctor; grader probe | a file that is not a database and a database with damaged pages are both detected and refused (tested); LIMITATIONS says doctor cannot repair; the path where integrity_check runs and returns errors is still never executed (the new test reaches the 'cannot be read' branch; grader probe; G1) |
| AC | Transactions | 9 | 9 | 9 | 9 | 9 | unit/test_db.py::test_write_tx_rolls_back |  |
| AC | Migration | 7 | 7 | 8 | 8 | 8 | unit/test_architecture.py::test_a_populated_first_release_database_upgrades_to_the_current_schema, ::test_a_failed_migration_leaves_the_earlier_ones_applied; unit/test_db.py::test_migrate_idempotent; docs/LIMITATIONS.md (Migrations) | as V Migration: limit written, but later migrations on populated tables are unproven |
| AC | Retention | 0 | 8 | 8 | 8 | 8 | unit/test_ops.py::test_retention_removes_only_expired_data_and_needs_the_owner; docs/LIMITATIONS.md (Retention never touches the audit log) | D4 fixed: LIMITATIONS now matches retention.py:23-26; evidence output tails and handover files are never pruned and removing superseded versions shortens `memory history`; both are written, but the first leaves part of the stored data outside any retention rule |
| AC | Privacy | 5 | 7 | 7 | 7 | 7 | unit/test_memory.py::test_secret_redacted_on_write; unit/test_comms.py::test_secrets_in_a_message_are_redacted_before_storage; retention test | unchanged since re-grade 3; audit payloads carry ids not text; deleted memory removable; evidence output tails and handover files are never erased; redaction pattern-based |
| AD | Queue performance | 0 | 7 | 7 | 7 | 7 | unit/test_ops.py::test_bench_measures_without_touching_the_live_ledger_and_flags_a_regression | unchanged since re-grade 3; admission queue p50/p95 and throughput measured; the regression guard is a manual `bench history`, not a CI gate; single machine |
| AD | Concurrency | 9 | 9 | 9 | 9 | 9 | concurrency/test_parallel_admission.py |  |
| AD | Load management | 8 | 8 | 8 | 8 | 8 | unit/test_admission.py::test_max_concurrent | unchanged since re-grade 3; caps only |
| AD | Resource forecasting | 7 | 7 | 7 | 7 | 7 | unit/test_intel.py::test_forecast_needs_history | unchanged since re-grade 3; linear, estimate-based |
| AD | Scaling efficiency | 0 | 6 | 6 | 6 | 6 | unit/test_ops.py::test_bench_measures_without_touching_the_live_ledger_and_flags_a_regression (admit_release_grown, slowdown_vs_empty) | unchanged since re-grade 3; one small growth point (a few hundred events); slowdown only asserted not None; no bound or stated scaling limit |
| AE | Code quality | 7 | 7 | 7 | 7 | 7 | ruff check src tests: All checks passed (run by grader) | unchanged since re-grade 3; no type checking |
| AE | Dependency management | 6 | 6 | 7 | 7 | 7 | unit/test_architecture.py::test_the_runtime_dependencies_are_exactly_pydantic, ::test_every_locked_dependency_is_pinned_with_hashes; unit/test_release_hygiene.py::test_the_lock_satisfies_the_declared_ranges | unchanged since re-grade 3; dependency set, lock completeness and lock-to-range agreement are tested; no update policy or automation |
| AE | Documentation | 5 | 8 | 8 | 8 | 8 | as A Documentation | as A Documentation: every reason has a message and a remedy (tested) and LIMITATIONS is now current for retention, `evidence run` and the automatic reap; no Python API reference; stale lines in reports/PHASE9_SCORES.md:39 and :45 and reports/AUDIT.md:360, :402 and :422 |
| AE | Testability | 8 | 8 | 8 | 9 | 9 | grader full run 969 passed, no skips, 96.22% branch; CI run 45926054163 on commit 6097cb6 (read by grader 3): 90% gate met on Windows and Ubuntu, Python 3.11 and 3.12; stated limit: live session tests are opt-in and macOS is untested (docs/LIMITATIONS.md, Hosts and Platform) |  |
| AE | Technical debt | 5 | 5 | 5 | 5 | 5 | docs/LIMITATIONS.md | unchanged since re-grade 3; no tracked debt items |
| AF | Installation usability | 7 | 7 | 7 | 7 | 7 | integration/test_install_script.py::test_dry_run_changes_nothing | unchanged since re-grade 3; Windows only |
| AF | Task visibility | 7 | 7 | 7 | 7 | 7 | integration/test_cli_task.py::test_task_flow_via_cli | unchanged since re-grade 3; no cited view test incl. empty/error |
| AF | Clear error messages | 8 | 8 | 8 | 8 | 8 | unit/test_hardening.py::test_a_refusal_prints_what_to_do; unit/test_ops.py::test_every_policy_refusal_names_a_reason, ::test_every_reason_has_a_remedy_and_a_meaning_and_none_is_stale; grader CLI probes (remedy line under each reason) | the remedy is now printed under the reasons and the fixed-text limit is written; but only in text mode: the `--json` error body (cli/__init__.py:151-155) has error, exit_code and reasons and no remedy, and the skill tells hosts always to pass `--json` (definitions/skills/agentos/SKILL.md:13), so the agent never sees it; not stated in LIMITATIONS (G4) |
| AF | Configuration clarity | 5 | 7 | 8 | 8 | 8 | unit/test_ops.py::test_the_breaker_is_a_policy_change_and_milder_needs_the_owner; `policy show` | unchanged since re-grade 3; the breaker is now in `policy show`; generic settings are not; no config file |
| AF | Owner controls | 9 | 9 | 9 | 9 | 9 | see G |  |
| AG | Existing framework integration | 0 | 5 | 5 | 5 | 5 | MCP tests (see N) | unchanged since re-grade 3; standard protocol server built and tested; no named agent framework connected or tested |
| AG | ECC compatibility | 6 | 6 | 6 | 6 | 6 | unit/test_adapters.py::test_check_* | unchanged since re-grade 3; no live session with both loaded; BLOCKED: live session uses the owner's quota |
| AG | Portable skills | 7 | 7 | 7 | 7 | 7 | unit/test_gen.py | unchanged since re-grade 3; live skill-follow unproven; BLOCKED: live skill-follow runs (quota) |
| AG | Adapter architecture | 8 | 8 | 8 | 8 | 8 | unit/test_adapters.py::test_install_refuses_a_folder_it_does_not_own | unchanged since re-grade 3; no third host verified |
| AG | Standard schemas | 4 | 7 | 7 | 7 | 7 | unit/test_ops.py::test_committed_schemas_match_the_models | unchanged since re-grade 3; freshness test only: no test validates a real `--json` output or plan against a schema and no invalid-record refusal; the hand-written plan schema allows `parent`, which `workflow save` refuses |
| AH | Benchmark protection | 8 | 8 | 8 | 8 | 8 | unit/test_improve.py::test_a_challenger_that_copies_a_held_out_case_is_refused | unchanged since re-grade 3; textual leakage check |
| AH | Reviewer independence | 8 | 8 | 8 | 8 | 8 | see Q | unchanged since re-grade 3; identity unauthenticated |
| AH | Score calibration | 0 | 6 | 6 | 6 | 6 | unit/test_ops.py::test_calibration_flags_an_evaluator_far_from_the_others | unchanged since re-grade 3; evaluator bias detection built and tested with a negative case; the scoring weights themselves are still uncalibrated against outcomes |
| AH | Evidence traceability | 9 | 9 | 9 | 9 | 9 | security/test_phase1_defects.py::test_d06_* |  |
| AH | Resistance to manipulation | 5 | 5 | 5 | 5 | 5 | unit/test_performance.py | unchanged since re-grade 3; a host can mint many evaluator ids |
| AI | Subscription efficiency | 3 | 3 | 3 | 3 | 3 | by inspection | unchanged since re-grade 3; host usage invisible; BLOCKED: hosts expose no subscription usage |
| AI | Long-term maintenance | 5 | 5 | 5 | 5 | 5 | none | unchanged since re-grade 3; no maintenance policy |
| AI | Dependency sustainability | 5 | 5 | 6 | 6 | 6 | unit/test_architecture.py::test_the_runtime_dependencies_are_exactly_pydantic | unchanged since re-grade 3; the one-dependency rule is enforced by a test; no maintenance or update policy |
| AI | Operational overhead | 4 | 5 | 5 | 5 | 5 | bench (AgentOS ops on scratch DB) | unchanged since re-grade 3; op latency measured, not per-command overhead; no guard |
| AI | Incremental extensibility | 5 | 5 | 5 | 5 | 5 | see A Extensibility | unchanged since re-grade 3; no plugin API |
| AJ | Provider usage restrictions | 4 | 4 | 7 | 8 | 8 | unit/test_architecture.py::test_nothing_in_agentos_opens_a_network_connection, ::test_a_network_connection_in_a_test_is_refused; tests/conftest.py no_network fixture; unit/test_hardening.py::test_external_commands_are_recognised | shell wrappers are now looked through (D3 mostly fixed); subprocesses can still open connections (stated in LIMITATIONS); package runners and managers (`npx`, `uvx`, `poetry install`, `conda install`, `go get`, `pip3.12 install`) are not flagged and not named in LIMITATIONS (grader probe; G3) |
| AJ | Authorization | 9 | 9 | 9 | 9 | 9 | see G |  |
| AJ | Data handling | 5 | 7 | 7 | 7 | 7 | as AC Privacy | unchanged since re-grade 3; as AC Privacy |
| AJ | External action boundaries | 4 | 4 | 4 | 6 | 8 | unit/test_hardening.py::test_external_commands_are_recognised, ::test_local_checks_are_not_flagged, ::test_an_external_command_is_refused_without_the_owner_and_the_refusal_is_kept, ::test_the_owner_can_allow_an_external_command, ::test_the_cli_asks_the_owner_before_an_external_command, ::test_without_a_terminal_the_cli_refuses_and_records_it; grader probes | D2 fixed (CLI without a terminal: exit 3, `external_action`, `evidence.refused` recorded; probe: two refusals, two events) and D3 mostly fixed (`cmd /c`, `bash -c`, `powershell -c`, `python -m pip`, pip, npm and uv installs caught); limit written; but `npx`, `uvx` and `pipx` are treated as harmless wrappers although they download packages, and `poetry install`, `conda install`, `winget install`, `go get`, `pip3.12 install`, `node -e` and `git ls-remote` pass (probe); the LIMITATIONS entry names only test scripts and `python -c` (G3) |
| AJ | License compliance | 4 | 4 | 4 | 7 | 8 | unit/test_release_hygiene.py::test_the_licence_rule_refuses_copyleft_and_unknown_licences (planted cases), ::test_every_locked_dependency_has_an_allowed_licence (no skips in my run); stated limit: not a legal review (docs/LIMITATIONS.md, Licences) | planted refusals now exist (GPL, LGPL, MIT AND GPL, empty, Proprietary); but the rule passes an unknown licence named next to an allowed one ('Proprietary AND MIT', 'LicenseRef-Proprietary AND BSD-3-Clause' pass; grader probe), against its own docstring, and an installed version that differs from the lock is skipped, not failed, while reports/AUDIT.md:402 says the installed version must be the locked one (G2) |
| AK | Backups | 8 | 8 | 8 | 8 | 9 | see Y Backup |  |
| AK | Restoration | 9 | 10 | 10 | 10 | 10 | see Y Restoration |  |
| AK | Interrupted tasks | 6 | 7 | 7 | 7 | 8 | unit/test_hardening.py::test_the_hook_reaps_stale_workers_at_most_every_five_minutes, ::test_the_hook_never_fails_a_worker_it_never_heard_from, ::test_a_worker_heard_from_within_the_hour_is_left_alone; unit/test_health.py (stale/reap tests); grader probe | as H Failure detection: no false positives now (D1 fixed); an interrupted task is found automatically only when its worker reported before, which the default hook config never records |
| AK | Recovery testing | 9 | 9 | 9 | 9 | 9 | resilience/test_resilience.py::test_backup_restores_real_work_and_keeps_a_safety_copy |  |
| AK | Recovery documentation | 5 | 8 | 8 | 8 | 8 | docs/RUNBOOK.md:16-24; unit/test_skill_commands.py::test_skill_command_parses; unit/test_architecture.py::test_a_failed_migration_leaves_the_earlier_ones_applied | unchanged since re-grade 3; migration wording fixed and backed by a test; no procedure is executed end to end by a test |
| AL | CLI usability | 7 | 7 | 7 | 8 | 9 | unit/test_hardening.py::test_a_mistyped_command_gets_a_suggestion, ::test_a_mistyped_command_far_from_any_gets_no_guess; unit/test_skill_commands.py; grader probe (`task ad` suggests add); stated limit: a mistyped option gets no suggestion (docs/LIMITATIONS.md, Error handling; probe `--prioirty` confirms) |  |
| AL | Configuration validation | 9 | 9 | 9 | 9 | 9 | unit/test_governor.py::test_unknown_limit_rejected |  |
| AL | Examples | 6 | 7 | 7 | 7 | 7 | docs/EXAMPLES.md; unit/test_skill_commands.py::test_the_guides_show_commands | unchanged since re-grade 3; examples parse but are never executed |
| AL | Debugging | 5 | 7 | 7 | 7 | 7 | docs/TROUBLESHOOTING.md; unit/test_ops.py::test_timeline_counts_each_day_and_spans_follow_each_worker | unchanged since re-grade 3; spans, timeline, incidents and policy history exist; no verbose/trace mode; spans are worker-level |
| AL | Troubleshooting | 6 | 7 | 8 | 8 | 9 | docs/REASONS.md (102 reasons); unit/test_ops.py::test_every_reason_has_a_remedy_and_a_meaning_and_none_is_stale, ::test_commands_named_in_remedies_parse; unit/test_hardening.py::test_a_refusal_prints_what_to_do; stated limits: doctor gives a fix hint for the database checks only, remedies are a fixed line per reason (docs/LIMITATIONS.md, Diagnostics and Refusal remedies) |  |
| AM | Alternative comparison | 2 | 6 | 6 | 6 | 6 | unit/test_ops.py::test_options_compare_alternatives_and_admit_uncertainty | host-model reasoning (AgentOS records, the host decides): unchanged since re-grade 3; worker templates compared side by side; strategic alternatives are not recorded with any decision |
| AM | Uncertainty handling | 1 | 6 | 7 | 7 | 7 | unit/test_ops.py::test_options_recommend_only_with_enough_history_on_both_sides, ::test_identical_grades_still_get_an_interval | host-model reasoning (AgentOS records, the host decides): unchanged since re-grade 3; Student t interval with a minimum half-width, `recommend` needs 3+ evaluations on both sides; LIMITATIONS now matches (N6 fixed); uncertainty appears only in `intel options` |
| AM | Risk analysis | 2 | 5 | 5 | 5 | 5 | unit/test_ops.py::test_options_compare_alternatives_and_admit_uncertainty | host-model reasoning (AgentOS records, the host decides): unchanged since re-grade 3; fixed per-option risk list; only `no_history` is asserted; no risk register |
| AM | Cost-benefit evaluation | 1 | 5 | 5 | 5 | 5 | unit/test_ops.py::test_options_compare_alternatives_and_admit_uncertainty | host-model reasoning (AgentOS records, the host decides): unchanged since re-grade 3; relative cost units; one arithmetic assertion; not recorded |
| AM | Decision traceability | 5 | 5 | 5 | 5 | 5 | unit/test_handover.py::test_create_and_resume_cross_host | unchanged since re-grade 3; no decision record type |
| AN | Project activation | 9 | 9 | 9 | 9 | 9 | unit/test_projects.py |  |
| AN | Memory isolation | 9 | 9 | 9 | 9 | 9 | security/test_memory_isolation.py |  |
| AN | Project budgets | 8 | 8 | 8 | 8 | 8 | unit/test_governor.py::test_budget_exceeded_and_release | unchanged since re-grade 3; host-reported usage; BLOCKED: runtime usage not exposed by hosts |
| AN | Cross-project coordination | 5 | 5 | 5 | 5 | 5 | unit/test_tasks.py::test_cross_project_dependency_denied | unchanged since re-grade 3; no shared work items |
| AN | Project-specific governance | 4 | 8 | 8 | 8 | 8 | unit/test_ops.py::test_a_project_limit_only_tightens_and_loosening_it_needs_the_owner, ::test_admission_enforces_the_project_slot_limit | unchanged since re-grade 3; per-project limits tighten only, loosening needs the owner; only max_concurrent enforcement is tested (max_depth / agents_per_task via get_limits untested); no per-project policies beyond limits; not in LIMITATIONS |
| AO | Dependency provenance | 5 | 6 | 7 | 8 | 8 | unit/test_architecture.py::test_every_locked_dependency_is_pinned_with_hashes; CI run 45926054163 on commit 6097cb6 (grader read the job logs with the read-only gh CLI) (audit job) | unchanged since re-grade 3; hash pins and the dependency audit are proven in a real run; provenance is PyPI hashes only, with no attestation check; the CI proof is outside tests/ |
| AO | Version pinning | 5 | 6 | 8 | 8 | 9 | unit/test_architecture.py::test_every_locked_dependency_is_pinned_with_hashes; unit/test_release_hygiene.py::test_the_lock_satisfies_the_declared_ranges, ::test_the_range_check_catches_a_planted_mismatch, ::test_the_hash_check_catches_a_planted_unhashed_pin; CI run 45926054163 (tamper refusal, read by grader 3); stated limit: build tools are not hash-checked (docs/LIMITATIONS.md, Hashes cover the locked dependencies) |  |
| AO | Release reproducibility | 0 | 4 | 4 | 6 | 6 | CI run 45926054163 on commit 6097cb6 (grader read the job logs with the read-only gh CLI): reproducible-build job built the wheel twice with the same sha256 and the wheel installed and ran `agentos --version` | unchanged since re-grade 3; proven in CI only, with no test in tests/ (rule 1 caps the row below 7); both builds ran on one runner; the wheel still lacks definitions/ (in LIMITATIONS) |
| AO | Update safety | 7 | 7 | 7 | 7 | 7 | unit/test_gen.py::test_generator_preserves_human_edits | unchanged since re-grade 3; no package update path |
| AO | Rollback verification | 5 | 5 | 5 | 5 | 5 | integration/test_cli_system.py::test_backup_then_restore_roundtrip | unchanged since re-grade 3; no release rollback |

## 3. Counts

| Score | Baseline | Re-grade 1 | Re-grade 2 | Re-grade 3 | Re-grade 4 |
| --- | --- | --- | --- | --- | --- |
| 10 | 1 | 3 | 3 | 3 | 3 |
| 9 | 38 | 35 | 36 | 37 | 53 |
| 8 | 56 | 68 | 79 | 86 | 75 |
| 7 | 21 | 39 | 42 | 37 | 33 |
| 6 | 22 | 29 | 22 | 23 | 22 |
| 5 | 39 | 26 | 24 | 24 | 24 |
| 4 | 14 | 10 | 4 | 0 | 0 |
| 3 | 2 | 2 | 2 | 2 | 2 |
| 2 | 4 | 0 | 0 | 0 | 0 |
| 1 | 7 | 1 | 1 | 1 | 1 |
| 0 | 9 | 0 | 0 | 0 | 0 |
| **9 or above** | **39** | **38** | **39** | **40** | **56** |

Re-grade 4 against re-grade 3: raised 21, lowered 0, unchanged 192. Rows below 9: 157, of which BLOCKED by an external limit: 30; host-model reasoning by design: 12; fixable in code, tests or docs: 115.

Rows that moved: A Separation of concerns 8 to 9; A Dependency boundaries 8 to 9; B Escalation 8 to 9; C Dynamic departments 8 to 9; F Knowledge preservation 8 to 9; H Failure detection 7 to 8; H Recovery 7 to 8; K Provenance 8 to 9; M Routing evidence 8 to 9; Q Acceptance criteria 8 to 9; R Error handling 8 to 9; R Circuit breakers 8 to 9; W Workflow reuse 8 to 9; Y Backup 8 to 9; AJ External action boundaries 6 to 8; AJ License compliance 7 to 8; AK Backups 8 to 9; AK Interrupted tasks 7 to 8; AL CLI usability 8 to 9; AL Troubleshooting 8 to 9; AO Version pinning 8 to 9.

The BLOCKED and host-reasoning groups are counted from the row text (a reason that names BLOCKED, or one that
starts "host-model reasoning"). Counted the same way, re-grade 3's rows give the same 30 and 12 it reported. No
BLOCKED row could move: there is still no Codex model quota (so no live session), no host stop API, and no
host token, cost or usage data. Every BLOCKED row in the table names its limit.

## 4. Status of D1 to D10

| # | Status | Evidence |
| --- | --- | --- |
| D1 automatic reap failed busy workers | FIXED | runtime.py:249-269 calls `health.reap(..., AUTO_REAP_AFTER_MIN (60), heard_from_only=True)`; health.py:81-82 skips workers with no heartbeat; runtime.py:287-288 runs the check on PreToolUse only. Tests test_the_hook_never_fails_a_worker_it_never_heard_from, test_a_worker_heard_from_within_the_hour_is_left_alone, test_start_and_stop_events_do_not_run_the_check pass. My probe: a worker never heard from, 3 hours busy, stayed RUNNING through its own SubagentStop and another spawn; a heard-from worker silent 61 minutes was reaped. Residual, stated in LIMITATIONS: under the default hook config nothing is ever reaped automatically |
| D2 CLI refusal lost its reason and record | FIXED | cli/cmd_evidence.py:32-39 swallows the owner prompt's refusal and lets `evidence.run` refuse; test_without_a_terminal_the_cli_refuses_and_records_it asserts `external_action` and one evidence.refused event; my probe: exit 3, `external_action`, two refusals recorded two events |
| D3 shell wrappers and installs passed | PARTLY | evidence.py:31-73 now looks through cmd, bash, sh, powershell, pwsh, env, python and others, and counts pip, uv, npm, yarn, pnpm and cargo installs (14 recognised and 10 local cases tested; probe confirms). Still not flagged (probe): `npx` and `uvx` (listed as harmless wrappers although they download packages), `poetry install`, `conda install`, `winget install`, `go get`, `pip3.12 install`, `node -e` code, `git ls-remote`. LIMITATIONS now has an entry, but it names only test scripts and `python -c` (G3) |
| D4 stale retention text | FIXED | docs/LIMITATIONS.md:155-160 now says deleted or superseded memory ages from the deletion or correction, as retention.py:23-26 does |
| D5 untested cleanup and OSError branches | FIXED | test_a_failed_copy_leaves_no_half_written_backup and test_a_file_error_is_exit_2_without_a_traceback pass; my coverage shows db.py:129-132 and the OSError branch of cli/__init__.py executed |
| D6 every database error called damage | FIXED | cli/__init__.py:120-133 `_database_error`: locked or busy exit 2, damaged exit 5 with restore advice, other errors exit 5 without it; test_database_errors_are_told_apart covers four cases |
| D7 empty health.reaped events | FIXED | health.py:95-96 returns without an event when the automatic check reaped nothing; the reap test counts one event after an empty check; my probe: the empty check added none |
| D8 memory.correct accepted an empty author | FIXED | memory.py:160-161; test_a_correction_without_its_author_is_refused; my probe refused '' and '  ' |
| D9 bad-input sweep accepted exit 0 | FIXED | tests/unit/test_hardening.py:346 now asserts the exit code is 2, 3, 4 or 5 |
| D10 licence check and scores-file job count | PARTLY | fixed: planted licence cases (test_the_licence_rule_refuses_copyleft_and_unknown_licences), planted range and unhashed-pin cases, and the citation check over PHASE9_SCORES.md, PHASE9_DELIVERABLES.md and COMPATIBILITY.md; no package was skipped in my run. Not fixed: the rule still ends in a substring test, so an unknown licence named next to an allowed one passes (probe), an installed version that differs from the lock is skipped rather than failed, and reports/PHASE9_SCORES.md:45 still says seven jobs (G2, G5) |

## 5. New defects found in this round

- **G1.** tests/unit/test_hardening.py:256-284 (`test_doctor_reports_damage_inside_a_readable_database`). The
  scribbled database makes SQLite raise "database disk image is malformed", so doctor takes the exception
  branch (src/agentos/cli/cmd_system.py:66-69, "cannot be read ... restore a backup"), not the branch where
  `PRAGMA integrity_check` runs and returns errors (cmd_system.py:59-61). How I know: I ran the test's recipe
  in a scratch home (grader4_probe_doctor.py); the detail was "cannot be read (database disk image is
  malformed)" and no schema_version check was produced. The claim "doctor on damage inside a readable
  database" is therefore not what the test proves; the integrity-result path is still never executed.
- **G2.** tests/unit/test_release_hygiene.py:90-97 (`_allowed`). Its docstring says one unknown name is
  enough to refuse, but the final test is `any(allowed in licence)`, a substring match, so 'Proprietary AND
  MIT', 'MIT | Proprietary', 'LicenseRef-Proprietary AND BSD-3-Clause' and 'UNLICENSED BSD' are allowed (my
  probe). Lines 114-115 skip, rather than fail, a package whose installed version differs from the lock, while
  reports/AUDIT.md:402 says "the installed version must be the locked one".
- **G3.** src/agentos/evidence.py:31-41. `npx`, `uvx` and `pipx` are in WRAPPERS, so they are treated as
  harmless launchers although each downloads and runs a package; `poetry`, `conda`, `winget`, `go`, `node`
  and versioned names such as `pip3.12` are in no table; `git ls-remote` is not a listed subcommand. All of
  these returned None in my probe. docs/LIMITATIONS.md (section "`evidence run` refuses the obvious outside
  commands") names only test scripts and `python -c` as misses.
- **G4.** src/agentos/cli/__init__.py:151-155. The new remedy line is printed only in text mode; the
  `--json` error body carries error, exit_code and reasons but no remedy, and the skill tells hosts "Always
  pass `--json`" (definitions/skills/agentos/SKILL.md:13), so the agent that meets a refusal never sees what
  to do. Seen by reading the code and by my probes (F2 JSON body has no remedy). Not in LIMITATIONS.
- **G5.** Stale report text: reports/PHASE9_SCORES.md:45 says CI "passed all seven jobs" (six), :39 says N9
  is "not fixed" (it was fixed in round 3), and :14 still gives the re-grade 2 result with no re-grade 3
  column; reports/AUDIT.md:360 and :422 say 100 reasons (docs/REASONS.md has 102). Seen by grep.

## 6. Top 15 fixable gaps (largest effect first)

1. **AJ External action boundaries and Provider usage restrictions (8):** treat `npx`, `uvx`, `pipx` as
   external, add poetry, conda, winget, go, node and versioned pip names and `git ls-remote`, test each, and
   name the remaining misses in LIMITATIONS (G3). Both rows could reach 9.
2. **AF Clear error messages (8):** put the remedy in the `--json` error body (a `remedies` map), test it,
   and the row can reach 9 (G4).
3. **H Failure detection, H Recovery, AK Interrupted tasks (8):** make the default hook config record a
   heartbeat (or ship `--guard-tools` as the default the installer writes) so the automatic check covers the
   default setup, with a test through the generated hooks file; prove agent_id on Codex tool calls when quota
   allows.
4. **AJ License compliance (8):** require every named licence to be allowed (SPDX expression parse, no
   substring), fail on a version mismatch instead of skipping, add 'Proprietary AND MIT' as a planted case,
   and correct reports/AUDIT.md:402 (G2).
5. **Y Diagnostics and AC Database consistency (8):** a test where `PRAGMA integrity_check` runs and returns
   errors (for example a corrupted index page, or a monkeypatched connection), rename the current test (G1),
   and add a pending-migration check to doctor.
6. **Z No fabricated quality scores, A and AE Documentation (8):** rebuild reports/PHASE9_SCORES.md with the
   re-grade 3 and 4 columns, fix the job count and the N9 line, fix the reason counts in AUDIT.md (G5); add a
   test that the counts in the reports match the generated reason table. A Python API reference is still
   needed for the documentation rows.
7. **AO Release reproducibility (6):** a test in tests/ that builds the wheel twice offline and compares the
   hashes, and ship definitions/ as package data.
8. **Y Updates (5):** an `agentos update` command with a test that upgrades an installed older version that
   holds data.
9. **S Supply-chain security and AO Dependency provenance (8):** an offline test in tests/ (`pip --no-index
   --find-links` on a local wheel with a wrong hash) so the install-time tamper refusal is part of the
   regression, not only CI.
10. **V Migration and AC Migration (8):** fixture databases at every schema version with rows in every
    table, each migrated to the current schema.
11. **AC Retention (8) and AC Privacy (7):** retention rules for evidence output tails and handover files,
    tested with the owner refusal.
12. **A Configuration design (7):** `agentos settings show/set` with a schema, routed through governance and
    the policy log.
13. **V Skill versioning (7):** a version-to-hash map in plugin.toml that fails when a new skill hash is
    paired with a version already listed.
14. **M Fallback behavior (7) and M Availability checks (8):** a CLI test of `intel route --host` picking a
    fallback, and a host-reported availability input (for example from `doctor` reading the host CLI's model
    list) so availability is not only the hand-written table.
15. **N MCP integration (8):** connect a reference MCP client in CI (list and call tools, refuse a pending
    migration).
