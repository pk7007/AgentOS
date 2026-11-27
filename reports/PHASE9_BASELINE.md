# AgentOS baseline grades (independent auditor)

Rubric: `reports/AUDIT_CRITERIA.md`. Source rows: `reports/AUDIT.md`, domains A to AO (AM's five criteria are
listed in prose there and are graded as five rows here). Every cited test was checked by name in `tests/`.
These test files were run read-only and passed (199 passed): `tests/security/*`, `unit/test_admission.py`,
`test_governance.py`, `test_runtime.py`, `test_improve.py`, `test_audit.py`, `test_workforce.py`, `test_intel.py`.
A second targeted run (the rest of `unit/`, `resilience/`, `concurrency/`) was refused by the environment's
permission check, so for tests in those files I confirmed they exist and read them; I did not see them pass.
A row is not scored 9 or 10 unless a refusal or failure-case test exists. Uncalibrated thresholds count as a stated
limit (9) only when the criterion is about the mechanism. When the criterion is about the quality of an output
those thresholds decide, they count as an unproven part (8 at most).

| Domain | Criterion | Score | One-line reason | What would raise it to 9+ |
| --- | --- | --- | --- | --- |
| A | Modularity | 6 | One module per concern with its own tests, but no test enforces the module boundaries | An import-boundary test (AST or import-linter) that fails on a forbidden cross-module import |
| A | Extensibility | 5 | Command registry and host profiles work (`test_host_generate_uses_profile`); no third-party plugin API | A documented extension API with a test that loads an external plugin and refuses a malformed one |
| A | Separation of concerns | 4 | Grep confirms core never imports `cli`, but no automated test proves it | A test that fails when any core module imports `agentos.cli` |
| A | Dependency boundaries | 4 | One runtime dependency in `pyproject.toml`; nothing fails if a new one is added | A CI test that asserts the allowed runtime dependency set |
| A | Architectural simplicity | 4 | No daemon or network by inspection; no test asserts it | A test that blocks sockets during the suite and asserts there are no network imports |
| A | Configuration design | 5 | Limits and budgets in the DB are validated; there is no CLI config file | A validated config file (with schema and refusal tests) plus documented precedence |
| A | Documentation | 5 | README with a command reference and seven docs; no API reference | A generated API/CLI reference that is checked against the parser in CI |
| B | Objective understanding | 6 | Refuses an objective that has no acceptance criteria; whether the objective is understood is never measured | Measured objective-to-outcome fidelity on real objectives, plus the refusal test |
| B | Planning | 6 | Plans are atomic and validated, with refusal tests; decomposition quality is not measured and the heuristics are uncalibrated | Plan quality graded against outcomes; complexity weights calibrated |
| B | Decision-making | 5 | Critical-path and capacity scheduling is tested but is only advice | Decisions enforced or measured against outcomes |
| B | Delegation | 8 | Depth and `can_delegate` refusals are tested; enforcement against a non-cooperating Codex host is not proven live | A live Codex spawn through the hook refusing an unadmitted child |
| B | Coordination | 5 | Dependencies and `task ready` only; no messaging between agents | An agent-to-agent channel or blackboard with isolation and refusal tests |
| B | Accountability | 9 | Every state change and denial is audited; the chain is tamper-evident; the unkeyed-chain limit is documented | (10) A keyed or anchored chain by default |
| B | Escalation | 5 | Escalation is recorded and owner-gated; the owner is never notified directly | Direct owner notification with a tested delivery or failure path |
| C | Clear authority | 9 | Forged confirmations and env-var bypasses are refused; the console-trust limit is in LIMITATIONS | (10) Owner identity that does not rely on the console alone |
| C | Role separation | 8 | Self and parent/child grading are refused, but evaluator identity is unauthenticated, so roles can be spoofed | Per-agent credentials issued by the runtime, with a spoofed-id refusal test |
| C | Dynamic departments | 8 | Creation and dissolution are tested, including the not-justified case; ledger records only, thresholds hand-picked | Thresholds calibrated, or the limit stated in LIMITATIONS as not affecting the job |
| C | Managerial effectiveness | 0 | Nothing exists | A measure of lead or department outcomes over real objectives, with tests |
| C | Organizational adaptability | 5 | Templates and weights change only through validated experiments; not measured across real objectives | Adaptation measured over real objectives |
| D | Capability detection | 8 | A gap is reported instead of a template being invented; matching is by tag, with no refusal for fuzzy mismatches documented | Document the tag-matching limit; add a test for near-miss capabilities |
| D | Candidate selection | 8 | Ranking is tested, and high-risk work requires a proven template; the weights are uncalibrated, so selection quality is unproven | Calibrated weights against outcomes |
| D | Onboarding | 7 | Template add, seed and factory registration are tested; brand-new templates get no probation | Probation for new templates, with a failing-probation test |
| D | Validation | 6 | Safety and schema validation, with refusal tests; no behavioural test of a new template before use | A behavioural trial gate before first use, with a failing-trial test |
| D | Recruitment efficiency | 5 | Reuse of templates and of open proposals is tested; efficiency is not measured | Measured time and cost of recruitment, with a regression guard |
| E | Recursive delegation | 8 | Depth cap refusal is tested; the live gate is proven only on the second host, not on Codex | A live Codex hook run refusing a too-deep spawn |
| E | Concurrency | 9 | 12 processes race and exactly 4 are admitted; the without-hooks limit is documented | (10) Live hook enforcement on both hosts |
| E | Workload adaptation | 8 | Split by effort and free slots, with refusals; effort figures are host-supplied estimates | Effort validated against outcomes |
| E | Overhead management | 6 | Only the `max_agents_per_task` cap; no overhead measurement | Measured coordination overhead, with a budget and a refusal |
| E | Workforce contraction | 8 | Slots are freed and contract is tested; running native workers are reported, not stopped | A native stop through the host, confirmed by test |
| F | Performance diagnosis | 8 | Bands, critical-visible and external-cause-excluded are tested; the weights are uncalibrated, so diagnostic accuracy is unproven | Calibrated against real outcomes |
| F | Rehabilitation | 9 | Probation pass and fail, and permission widening refused, are tested; the thresholds are documented as hand-picked | (10) Calibrated thresholds |
| F | Suspension | 9 | Suspension after consecutive failures, retirement left to the owner, reinstatement: all tested; the limits are documented | (10) Calibrated thresholds |
| F | Safe cancellation | 6 | The ledger holds the slot until the stop is confirmed; AgentOS cannot stop a native worker, and guard-tools is unverified on Codex | A native kill path, or guard-tools verified live on Codex |
| F | Replacement | 7 | Transfer is tested with refusal (the old worker keeps running); stopping the old native worker is a manual host step | Host-side stop wired and tested |
| F | Knowledge preservation | 8 | Termination and transfer notes, plus failure lessons, are tested; happy path only, and the note is host-written | A test that refuses or flags termination with no note |
| G | Owner authority | 9 | Many refusal tests (forge, raise limit, retire, restore); the console-trust limit is documented | (10) A PIN that is mandatory, or stronger owner auth |
| G | Approval requirements | 9 | Approvals are bound to parameters, single-use and expiring; denying a granted one is refused; the console limit is documented | (10) Stronger owner identity |
| G | Policy enforcement | 6 | Admission refuses with reasons; the hook gate is live on the second host only; Codex is unproven, and hosts without hooks only cooperate | A live Codex spawn refusal through the trusted hook |
| G | Emergency controls | 8 | The stop blocks admission and spawn, and lifting it needs the owner; running subagents cannot be killed (guard-tools is unverified on Codex) | Emergency stop proven to halt running workers live |
| G | Independent oversight | 8 | Evaluator independence is enforced and intel governance catches 8 planted violations; evaluator identity is unauthenticated | Authenticated evaluator identity |
| H | Failure detection | 5 | FAILED state, retry limit and orphan warning on resume; no heartbeat | A heartbeat or stale-worker detection with a missed-heartbeat test |
| H | Recovery | 6 | Retry with a different template and escalation are tested; the host must start the retry | An automated retry start through the host, tested |
| H | Checkpointing | 8 | Handovers with refusals (second resume, bad id, wrong repo); manual and host-written, with no automatic checkpoint | Automatic checkpoints at state changes, tested |
| H | Reassignment | 8 | Transfer is tested, including the refused case; the host must stop the old native worker | Native stop wired and tested |
| H | Fault isolation | 8 | A security flag quarantines the template and instance, and admission refuses non-active templates; no direct test that a quarantined template is refused | A test admitting a quarantined template and expecting `template_unavailable` |
| I | Decision quality | 5 | `compete` ranks on independent evaluations only; the host makes the decisions | Decision outcomes measured |
| I | Context understanding | 5 | Context pack ordering and budget are tested; understanding is not measured | A relevance benchmark for the context pack |
| I | Capability matching | 8 | Same as D candidate selection: tested, weights uncalibrated | Calibrated weights |
| I | Evidence synthesis | 6 | Evaluations require AgentOS-run `evd_` records (free text refused); the synthesis is the host's | Evidence-to-claim linking checked automatically |
| I | Organizational effectiveness | 6 | `intel org` passes planted positive and negative cases; there is no outcome benchmark over time | A longitudinal effectiveness metric |
| J | Task decomposition | 5 | Parent tasks and the depth limit (refusal) are tested; the host decomposes | Decomposition quality checks |
| J | Dependency management | 10 | Cycle, self-dependency, deps-not-done and cross-project refusals; the race was fixed in one transaction (D11); documented in the README | None needed |
| J | Scheduling | 6 | Boss advisory schedule (critical path, capacity) and `task ready`; there is no enforcing scheduler | An enforced schedule, or admission ordering, tested |
| J | Prioritization | 8 | Priority ordering is tested; happy path only | A test with ties, invalid priorities and a refusal |
| J | Execution state | 9 | Illegal transitions are refused and audited, and re-entry runs admission (D04); native state is only what the host reports (documented) | (10) Native state confirmed by the runtime |
| K | Memory quality | 5 | Dedupe, length limit and redaction; no quality scoring | Quality scoring, with low-quality refusal tests |
| K | Provenance | 8 | Source, author and confidence round-trip; no refusal test for missing provenance | Refuse writes without provenance, and test it |
| K | Retrieval | 8 | FTS5 search, safe with special characters; keyword-only (documented), which misses paraphrases | Semantic or synonym retrieval, or a documented retrieval benchmark |
| K | Versioning | 8 | `correct` supersedes the old record; happy path only | A test that history is kept and that superseding another project's record is refused |
| K | Knowledge transfer | 9 | Only validated org records cross projects; unvalidated and cross-project reads are refused; the keyword limit is documented | (10) Transfer measured for reuse |
| L | Feedback capture | 9 | All scores, evidence, no duplicates and no self-grading are enforced (D05 to D07); evaluator authentication is a documented limit | (10) Authenticated evaluators |
| L | Failure analysis | 8 | Retro diagnoses weaknesses and recurring mismatches; thresholds hand-picked; no negative-case retro test | A negative case (a healthy record gives no diagnosis) and calibrated thresholds |
| L | Improvement hypotheses | 7 | Rule-based fixed addenda only; the host may propose its own | Richer hypothesis generation, tested against outcomes |
| L | Experimentation | 8 | Champion versus challenger with rejections, gate and flags; the small case counts are documented | Larger or statistically justified samples |
| L | Learning retention | 5 | Memory persists and promotions write org memory; reuse is not measured | A reuse metric with tests |
| M | Capability matching (routing) | 6 | Tier advice is tested; tiers are relative, there is no actual model routing, and the host maps tiers | Routing enforced or verified on a host, with a refusal case |
| M | Cost-quality balance | 6 | Advice tested, including the never-lower-critical rule; hand-picked thresholds; no real cost data | Real cost and quality data feeding the rule |
| M | Availability checks | 4 | `doctor` only reports whether the Codex CLI is on PATH; no model or quota availability check | Model and quota availability check with a failure test |
| M | Fallback behavior | 0 | Nothing exists (LATER, slice 4) | Fallback tiers with a test where the primary is unavailable |
| M | Routing evidence | 7 | Routes list their reasons and history (asserted in the intel tests); no test for a missing-history case | A test that routing without history says so |
| N | Codex compatibility | 7 | Install, enable and hook discovery proven locally with the real CLI; no live session (quota) | A live Codex session following the skill |
| N | Second host (`cc`) compatibility | 7 | Host validator passes and the live spawn gate ran, but from local settings, not the installed plugin | The live gate run from the installed plugin |
| N | Skills compatibility | 5 | Every skill command parses and score keys are real; a live host following the skill is BLOCKED | A live skill-follow run on both hosts |
| N | MCP integration | 0 | Nothing exists | An MCP server exposing the ledger, with tests |
| N | Hooks and plugin support | 6 | Real-CLI hook discovery, handler tests, live on `cc`; Codex live spawn not run; needs owner trust | A live Codex spawn through the hook |
| O | Logging | 8 | `audit log` lists events; happy path only | Filters and error cases tested; log levels documented |
| O | Metrics | 5 | Dashboard and observe views, tested; no time series | Time-series metrics with tests |
| O | Tracing | 5 | A parent/child tree is shown; no spans or timings | Span-level tracing with durations |
| O | Auditability | 9 | Tamper, deleted row, truncation and anchor checks are all tested; the unkeyed chain is documented | (10) A keyed chain or external anchor by default |
| O | Runtime visibility | 8 | `observe agents` shows slot holders with host-reported data; command line only, not live (documented) | A live or refreshing view, and Codex runtime data verified |
| P | Agent quality | 7 | Weighted, all-scores-required evaluations; the weights are uncalibrated, and the cited tests are mostly arithmetic | Calibrated weights validated against outcomes |
| P | Reliability | 5 | Failure rate and consecutive failures appear in summaries and drive suspension; no reliability metric test is cited | A dedicated reliability metric with tests |
| P | Latency | 1 | Only evidence `duration_ms` is recorded; no agent latency metric | Per-agent and per-task latency measured and tested |
| P | Resource efficiency | 5 | Token-estimate budgets are enforced; the figures are host-reported estimates | Real usage figures from the host runtime |
| P | Performance trends | 1 | Only the post-promotion monitor window looks at change over time; no trend view | Trend computation and display, with tests |
| Q | Acceptance criteria | 6 | Objectives need criteria, and `boss accept` needs independent passing evidence; the criteria are not checked against the evidence | Criteria mapped to evidence checks automatically |
| Q | Independent evaluation | 8 | Self and parent/child grading are refused; identity is unauthenticated | Authenticated evaluators |
| Q | Testing | 9 | 675 tests and 95% branch coverage on CI (2 OS x 2 Python); the row's 537 count is stale; macOS is untested (documented) | (10) macOS in CI and a coverage gate |
| Q | Regression prevention | 9 | CI lint and tests, a generated-plugin freshness test, a skill command test; the Codex test skips on CI (stated) | (10) Codex CLI in CI |
| Q | Evidence integrity | 9 | Evidence must exist and belong to the project (refused otherwise), and the audit chain is tamper-evident; "proves what ran, not what it means" is documented | (10) Semantic evidence checks |
| Q | Live host follows the skill | 3 BLOCKED | The live test is written but never run (quota); only static command parsing is proven | Run `pytest -m live` with the owner's go-ahead on both hosts |
| R | Error handling | 8 | Exit-code mapping and bad TOML/missing files are tested; coverage of error paths is spot-checked | A systematic error-path test (fuzz the CLI inputs; no tracebacks) |
| R | Idempotency | 8 | init, migrate and activate twice; repeated SubagentStop and the same spawn checked twice are idempotent | An idempotency test for every mutating command, or a documented list |
| R | Circuit breakers | 4 | Manual emergency stop and retry limit only; no automatic breaker | An automatic breaker on failure rate, with a tripping test |
| R | State consistency | 9 | Rollback, race and parallel-write tests (seen to exist and read; parallel admission passes); the direct-DB-write limit is documented | (10) Protection against direct DB writes |
| R | Failure recovery | 9 | Killed mid-write, busy DB waited for, backup/restore; limits documented | (10) Recovery of in-flight host work |
| S | Permission boundaries | 8 | Owner guard refusals (4 tests); agent tool permissions are enforced by the host, not by AgentOS | A runtime-enforced tool permission gate, tested live |
| S | Isolation | 9 | Project isolation tests and D17 cross-project refusals; the inspect leak was fixed; direct DB access is documented | (10) OS-level isolation of the DB |
| S | Secret protection | 8 | Pattern redaction with tests; pattern-based and documented, so unknown formats leak | Entropy-based detection, or refuse writes on suspected secrets |
| S | Injection resistance | 6 | FTS quoting, parameterised SQL, path containment; prompt injection is out of reach | Tested defences for prompt content reaching hosts (for example tainted-memory marking) |
| S | Supply-chain security | 5 | Lock file and pip-audit in CI; no hash pinning or signing | Hash-pinned lock (`--require-hashes`) and signed releases |
| T | Capability registry | 8 | Versioning and seed load tested; invalid schema refused elsewhere | Registry-specific refusal tests (duplicate or invalid capability) |
| T | Performance history | 8 | Bands and insufficient evidence tested; uncalibrated | Calibration |
| T | Promotion | 9 | Only through `improve decide`; weaker challengers rejected, failing gate blocks; small samples documented | (10) Larger samples |
| T | Reassignment | 8 | Same evidence as H reassignment; the native stop is the host's | Native stop wired |
| T | Succession planning | 8 | One test with planted successors and single points of failure; no negative case | A test with no successor and with a balanced org |
| U | Token efficiency | 1 | The host's tokens are invisible; only context-pack budgeting exists | Real token telemetry from the host, with efficiency measures |
| U | Context management | 8 | Compact handovers and a budgeted context pack, tested; token counts are 4-chars-per-token estimates | Real tokenizer counts, or validation of the estimate |
| U | Resource budgets | 8 | Budget exceeded and run-budget refusals tested; a host that never reports usage is never charged | Usage reported by the runtime, not the host |
| U | Duplicate-work prevention | 8 | Duplicate admission refused; memory dedupe, including in parallel; only exact duplicates are caught | Near-duplicate task detection, tested |
| U | Cost awareness | 8 | Paid spend blocked, above-cap needs the owner; costs are host-reported | Real cost data from the host |
| V | Agent versioning | 8 | Versioning and status across versions tested; no refusal case for version conflicts in the cited tests | A refusal test (for example a stale version update) |
| V | Skill versioning | 4 | The skill is versioned only with the plugin; no per-skill version | Per-skill versions with drift and refusal tests |
| V | Policy versioning | 2 | Limit changes are audited, not versioned; policy values have no version history beyond experiments | Versioned policy records with rollback tests |
| V | Migration | 7 | 7 migrations; idempotency and newer-schema refusal tested; no test upgrades an old populated DB; the row's "one migration" is stale | A test upgrading a v1 DB with data to the current schema |
| V | Rollback | 7 | DB restore, exact plugin rollback and promotion rollback are tested; no release rollback | Release-level rollback with a test |
| W | Execution graphs | 8 | Task DAG with cycle refusal; the host executes it | Graph execution tracked to completion, tested |
| W | Parallelism | 8 | Admission is concurrency-safe; actual parallel execution is the host's | Live parallel run proof |
| W | Communication | 1 | Nothing direct; only shared memory and handovers | An inter-agent messaging channel with tests |
| W | Conflict resolution | 1 | Nothing exists (`compete` ranks competing solutions but does not resolve conflicts) | Conflict detection and resolution (for example overlapping file edits), tested |
| W | Workflow reuse | 2 | Only proven commands turned into skills (intel); no reusable workflow templates | Saved, parameterised workflows with tests |
| X | Handover quality | 9 | Cross-host resume, HEAD/diverged and dirty-tree warnings, secrets excluded, single claim; summary-only is documented | (10) Live cross-host run |
| X | Configuration synchronization | 8 | Drift detection tested; `host check` reads files only (documented) | Resolved-config check through the host CLI |
| X | Shared learning | 7 | One store; the cross-host CLI test exists but is not cited in the row; local only, no live sessions | A live cross-host learning run |
| X | Session recovery | 9 | Single-claim and wrong-repo refusals tested | (10) Live run |
| X | Compatibility verification | 6 BLOCKED | Codex install and second-host validation proven; the live Codex session is BLOCKED (no quota) | Run the live tests when quota returns |
| Y | Installation | 7 | A real venv install test with dry run and old-Python refusal; Windows/PowerShell only; the PATH edit is untested | A cross-platform installer and a tested PATH edit |
| Y | Updates | 4 | Re-running the installer is the only path; no update command or upgrade test | An `update` command with an upgrade-from-old-version test |
| Y | Diagnostics | 8 | `doctor` statuses and audit-chain check tested; limited scope | More doctor checks, each with a failing-condition test |
| Y | Backup | 8 | Round trip and real-work restore tested; no backup failure case (for example an unwritable destination) | A backup failure-path test |
| Y | Restoration | 9 | Refuses non-SQLite and newer-schema files, owner-only, keeps a safety copy | (10) Documented runbook |
| Y | Uninstallation | 8 | Uninstall, purge-keeps-backup and dry run tested; Windows only | Cross-platform uninstall |
| Z | No fabricated agents | 9 | A gap is reported instead of a template being invented; factory output is validated | (10) Documented limit closed |
| Z | No fabricated test results | 7 | AgentOS-run evidence is required, but a host can run a command that proves nothing (documented) | Evidence semantics checks (for example required test-runner output parsing) |
| Z | No fabricated costs | 8 | Labelled "estimates only" (asserted in `test_handover`); bad amounts refused (D12) | Real cost data or a test that no cost is ever computed |
| Z | No fabricated performance | 9 | Fewer than 5 evaluations gives `insufficient_evidence`; empty summary tested | (10) Calibrated confidence |
| Z | No fabricated quality scores | 4 | The evidence is the report's own prose; no test, and the Phase 7 table does carry reviewer scores | A test that any published score cites evidence |
| AA | Improvement over baseline | 5 | Only the promotion mechanism is proven; no real improvement has been measured | A measured real improvement on real work |
| AA | Candidate validation | 9 | Isolation, safety re-check, failing gate and unsafe/identical refusals are tested; the gate runs the host's command (documented) | (10) A fixed security gate |
| AA | Regression detection | 8 | Rollback and adoption tested; the window and margin are uncalibrated, so sensitivity is unproven | Calibrated window and margin |
| AA | Reproducibility | 5 | Hashed fixed cases and audited steps; workers are non-deterministic | Repeat-run variance measured |
| AA | Learning transfer | 5 | Promotions write org memory; reuse is not measured | A reuse metric |
| AB | Experiment isolation | 9 | A candidate is admitted only on its own trials (refusal tested) | (10) Documented limit closed |
| AB | Versioned proposals | 8 | Versions are recorded and rollback re-adds the previous one; no refusal case for conflicting proposals | A conflicting-proposal refusal test |
| AB | Staged promotion | 9 | Trialing, promoted, then adopted or rolled back, including the failure path | (10) Calibrated stages |
| AB | No unauthorized self-modification | 9 | Non-tunable names and out-of-bounds values refused; hand replacement needs the owner; direct DB writes are a documented limit | (10) DB write protection |
| AB | Protected governance | 9 | Protected settings need the owner (refusal test); console limit documented | (10) Stronger owner auth |
| AB | Rollback | 7 | Promotion, DB and plugin rollback tested; no release rollback | Release rollback |
| AC | Database consistency | 8 | `integrity_check` in doctor, WAL, killed-process integrity test; no corrupted-DB detection test | A test that doctor flags a corrupted DB |
| AC | Transactions | 9 | Rollback, commit and append-outside-transaction refusal tested | (10) Documented limits |
| AC | Migration | 7 | Same as V migration | Old-DB upgrade test |
| AC | Retention | 0 | No pruning or retention policy | Retention policy with pruning that keeps the audit chain verifiable, tested |
| AC | Privacy | 5 | Local-only storage, redaction, delete wipes content; audit payloads are kept | Audit payload minimisation or erasure with the chain kept, tested |
| AD | Queue performance | 0 | Not benchmarked | Benchmarks with a regression guard |
| AD | Concurrency | 9 | Same as E concurrency | As E |
| AD | Load management | 8 | `max_concurrent` refusal and the parallel race; caps only, no adaptive load handling | Adaptive load shedding, tested |
| AD | Resource forecasting | 7 | The forecast is tested, including the needs-history refusal; linear in effort and estimate-based | A validated forecasting model |
| AD | Scaling efficiency | 0 | Nothing exists | Scaling measurements |
| AE | Code quality | 7 | `ruff` clean and enforced in CI; no type checking | mypy or pyright in CI |
| AE | Dependency management | 6 | One runtime dependency, lock file, pip-audit; no hash pinning | Hash-pinned lock |
| AE | Documentation | 5 | Same as A | API reference |
| AE | Testability | 8 | 95% branch coverage measured in CI, but no coverage threshold gates it | `--cov-fail-under` in CI |
| AE | Technical debt | 5 | LIMITATIONS lists the debt; no tracking or measure | Tracked debt items with owners and tests |
| AF | Installation usability | 7 | Dry run by default with every step printed, tested; Windows only | Cross-platform installer |
| AF | Task visibility | 7 | `task list`/`ready`/`status` covered by the CLI flow tests; no specific test cited | A cited view test, including empty and error states |
| AF | Clear error messages | 8 | Every denial reason listed; exit codes mapped | A message catalogue with tests for each refusal reason |
| AF | Configuration clarity | 5 | `limits show`/`budget show` only | A unified config view with docs and tests |
| AF | Owner controls | 9 | Same as G | As G |
| AG | Existing framework integration | 0 | Nothing exists | An adapter to at least one existing agent framework, tested |
| AG | ECC compatibility | 6 | The static check is tested, including the duplicate-install flag; no live session with both loaded | A live session with ECC and AgentOS both loaded |
| AG | Portable skills | 7 | One skill is generated to every host, with a freshness test; a live host following it is unproven | Live skill-follow runs |
| AG | Adapter architecture | 8 | Profiles and adapters tested, including refusal of a folder AgentOS does not own; other hosts unverified | A third host verified |
| AG | Standard schemas | 4 | `--json` output only; no published schema and no schema test | Published JSON schemas validated in tests |
| AH | Benchmark protection | 8 | Hidden held-out cases with leakage refusal tested; the leakage check is textual, so paraphrases pass (documented) | Semantic leakage detection |
| AH | Reviewer independence | 8 | Same as Q independent evaluation | Authenticated evaluators |
| AH | Score calibration | 0 | Not built; the weights are labelled uncalibrated | A calibration study wired into the weights |
| AH | Evidence traceability | 9 | Each evaluation cites a checked `evd_` of the same project; audited; refusals tested (D06) | (10) Semantic linkage |
| AH | Resistance to manipulation | 5 | No self or relative grading, two independent failing evaluators; a host can mint many evaluator ids | Authenticated evaluators or Sybil limits |
| AI | Subscription efficiency | 3 | AgentOS makes no model calls (by inspection), but host subscription usage is invisible and unmeasured | Host usage telemetry and efficiency measures |
| AI | Long-term maintenance | 5 | Small codebase, high coverage; no maintenance policy or process | Documented maintenance policy and automated dependency updates |
| AI | Dependency sustainability | 5 | stdlib plus pydantic; pip-audit in CI | A dependency policy test |
| AI | Operational overhead | 4 | No service to run (by inspection); no test | Measured overhead per command |
| AI | Incremental extensibility | 5 | Same as A extensibility | Plugin API |
| AJ | Provider usage restrictions | 4 | No provider APIs, by inspection only; no test | A no-network test |
| AJ | Authorization | 9 | Same as G | As G |
| AJ | Data handling | 5 | Same as AC privacy | As AC |
| AJ | External action boundaries | 4 | No network I/O by inspection, but `evidence run` executes arbitrary host commands; no test | A command allowlist or sandbox, with refusal tests |
| AJ | License compliance | 4 | MIT LICENSE present; no automated license check | A license scan in CI |
| AK | Backups | 8 | Same as Y backup | Backup failure test |
| AK | Restoration | 9 | Same as Y restoration | Runbook |
| AK | Interrupted tasks | 6 | Handovers and orphan warnings on resume only; no heartbeat or automatic detection | Automatic interrupted-work detection |
| AK | Recovery testing | 9 | Round trip, real-work restore with chain intact and safety copy, killed process | (10) Scheduled recovery drills |
| AK | Recovery documentation | 5 | README backup/restore and troubleshooting table; no runbook | A disaster-recovery runbook |
| AL | CLI usability | 7 | `--help` on every command; skill and README quickstart commands parse | Usability checks (for example suggestions on typos) |
| AL | Configuration validation | 9 | Unknown limit, invalid template schema, missing profile key and BOM: all tested | (10) A documented validation reference |
| AL | Examples | 6 | README quickstart is checked by a test; few examples | Tested worked examples per feature |
| AL | Debugging | 5 | `audit log` and `agent inspect` only | Debug or trace tooling |
| AL | Troubleshooting | 6 | `doctor` tested plus a README troubleshooting table | A doctor fix-hint for each failure, tested |
| AM | Alternative comparison | 2 | Not built for strategy; only `intel compete` ranks competing implementations | Recorded alternatives with comparison and tests |
| AM | Uncertainty handling | 1 | Only confidence fields and `insufficient_evidence` | Explicit uncertainty records in decisions |
| AM | Risk analysis | 2 | Task risk levels gate admission; there is no risk analysis | A risk register or analysis with tests |
| AM | Cost-benefit evaluation | 1 | Only the effort forecast exists | Cost-benefit records with tests |
| AM | Decision traceability | 5 | Decisions can be stored in memory layers and carried in handovers; no decision record type | A decision record type linked to evidence and audit |
| AN | Project activation | 9 | Activation, idempotency, path normalisation and inactive refusal tested | (10) Documented limits closed |
| AN | Memory isolation | 9 | Same as S isolation | As S |
| AN | Project budgets | 8 | Project-scope budgets tested; usage is host-reported | Runtime-reported usage |
| AN | Cross-project coordination | 5 | Cross-project dependencies refused; lessons shared after two projects validate them; no shared work | Shared cross-project work items with tests |
| AN | Project-specific governance | 4 | Only inactive-project refusal; limits are global | Per-project limits and policies with tests |
| AO | Dependency provenance | 5 | PyPI only; pip-audit and pip check in CI; no hash checking | `--require-hashes` lock |
| AO | Version pinning | 5 | Lock file used by CI; a user's `pip install -e` resolves ranges | Hash-pinned lock used by the installer |
| AO | Release reproducibility | 0 | No release build | A reproducible build with a hash comparison in CI |
| AO | Update safety | 7 | Hand edits preserved, backup before plugin update, exact rollback, refusal of a folder it does not own; no package update path | A safe package update path, tested |
| AO | Rollback verification | 5 | DB round trip and plugin rollback tested; no release rollback | Release rollback test |

## Counts per score

(213 rows; BLOCKED rows are counted at their proven score)

| Score | Count |
| --- | --- |
| 10 | 1 |
| 9 | 38 |
| 8 | 56 |
| 7 | 21 |
| 6 | 22 (one is BLOCKED) |
| 5 | 39 |
| 4 | 14 |
| 3 | 2 (one is BLOCKED) |
| 2 | 4 |
| 1 | 7 |
| 0 | 9 |

Two rows are BLOCKED: Q "Live host follows the skill" (3) and X "Compatibility verification" (6).

## Cited tests that could not be found

None. All 220 cited test references in the 41 domain sections resolve to an existing `def test_...` in the cited
file. Bare `::name` references were resolved by searching `tests/` (for example `unit/test_improve.py`,
`unit/test_intel.py`, `integration/test_cli_system.py`). Every cited file exists. Wildcards (`test_d06_*`,
`test_check_*`) match at least one test.

Stale or inaccurate row notes I found (they do not change the scores above):
- Q "Testing" cites 537 tests; the header now says 675.
- V "Migration" says "one migration so far"; `src/agentos/migrations/` holds 7.
- A, AE and AI rows make structural claims ("core never imports cli", "no network") that I confirmed by grep, but
  no automated test enforces them.
- X "Shared learning" and M "Routing evidence" cite no test, although supporting tests exist.
- `integration/test_install_script.py` is skipped off Windows, and `integration/test_codex_hook_discovery.py`
  is skipped when the Codex CLI is absent (always on CI).
