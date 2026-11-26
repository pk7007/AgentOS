"""Self-improvement: retrospectives, benchmark cases, champion-versus-challenger experiments with blind,
independently graded trials, a regression gate, promotion, monitoring and rollback."""

import sys

import pytest

from agentos import admission, boss, improve, memory, performance, recruit, tasks, templates
from agentos.admission import AdmitRequest
from agentos.db import get_setting
from agentos.errors import NotFound, PolicyDenied, UsageError
from agentos.templates import TemplateStatus
from agentos.util import new_id, now_iso
from tests.conftest import add_evidence, add_instance

PASS = [sys.executable, "-c", "pass"]
FAIL = [sys.executable, "-c", "raise SystemExit(1)"]
GUIDE = improve.GUIDANCE["reliability"]


def _cases(conn, project, rep=3, held=2, suite="core", command=PASS):
    ids = []
    for i in range(rep):
        ids.append(improve.add_case(conn, project.id, suite, f"representative case {i} parse the config file",
                                    command, "representative", "test", capabilities=["python"],
                                    acceptance=[f"config case {i} parses"])["id"])
    for i in range(held):
        ids.append(improve.add_case(conn, project.id, suite, f"hidden check {i} on unusual input widths",
                                    command, "heldout", "test", capabilities=["python"])["id"])
    return ids


def _propose(conn, project, changes=None, suite="core"):
    base = templates.get_template(conn, "implementer").instructions
    return improve.propose_template(conn, project.id, "implementer", changes or {"instructions": f"{base}\n{GUIDE}"},
                                    "explicit check guidance raises reliability", suite, "test")


def _run(conn, exp, case_id, arm, value, evaluator, flags=None):
    r = improve.start_trial(conn, exp.id, case_id, arm, "test", "test")
    assert r["status"] == "admitted", r
    conn.execute("UPDATE agent_instances SET state='COMPLETED' WHERE id=?", (r["instance_id"],))
    ev = improve.check_trial(conn, r["trial_id"], "test")
    e = performance.record_eval(conn, r["instance_id"], evaluator, "coding",
                                {k: value for k in performance.WEIGHTS}, [ev.id], flags=flags, actor="test")
    improve.score_trial(conn, r["trial_id"], e.id, "test")
    return r


def _trial_all(conn, project, task, exp, cases, champ=70, chal=80, held_chal=None):
    a, b = add_instance(conn, project, task), add_instance(conn, project, task)
    for i, cid in enumerate(cases):
        heldout = improve._case(conn, cid)["split"] == "heldout"
        ev = a if i % 2 else b
        _run(conn, exp, cid, "champion", champ, ev)
        _run(conn, exp, cid, "challenger", held_chal if heldout and held_chal is not None else chal, ev)


def _grade_version(conn, project, task, version, value, n=5):
    ev = add_instance(conn, project, task)
    for _ in range(n):
        iid, ts = new_id("ag"), now_iso()
        conn.execute(
            "INSERT INTO agent_instances(id, template_id, template_version, project_id, task_id, parent_id, depth,"
            " host, state, created_at, updated_at) VALUES (?, 'implementer', ?, ?, ?, NULL, 0, 'test',"
            " 'COMPLETED', ?, ?)", (iid, version, project.id, task.id, ts, ts))
        performance.record_eval(conn, iid, ev, "coding", {k: value for k in performance.WEIGHTS},
                                [add_evidence(conn, project.id)], actor="test")


# --- benchmark cases ----------------------------------------------------------------------------

def test_cases_validate_and_reject_duplicates(conn, project):
    with pytest.raises(UsageError):
        improve.add_case(conn, project.id, "core", "t", PASS, "training", "test")
    with pytest.raises(UsageError):
        improve.add_case(conn, project.id, "Core Suite", "t", PASS, "heldout", "test")
    with pytest.raises(UsageError):
        improve.add_case(conn, project.id, "core", "t", [], "heldout", "test")
    improve.add_case(conn, project.id, "core", "same", PASS, "heldout", "test")
    with pytest.raises(PolicyDenied) as e:
        improve.add_case(conn, project.id, "core", "same", PASS, "heldout", "test")
    assert e.value.reasons == ["duplicate_case"]


def test_held_out_cases_are_hidden_from_listings_and_the_audit(conn, project):
    _cases(conn, project)
    listed = improve.list_cases(conn, project.id, "core")
    held = [c for c in listed if c["split"] == "heldout"]
    assert len(held) == 2 and all("title" not in c and "check_command" not in c for c in held)
    assert all("title" in c for c in listed if c["split"] == "representative")
    payloads = [r[0] for r in conn.execute("SELECT payload FROM events WHERE kind='improve.case_added'")]
    assert not any("unusual input widths" in p for p in payloads)


# --- proposing experiments ------------------------------------------------------------------------

def test_an_experiment_needs_enough_cases(seeded, project):
    _cases(seeded, project, rep=3, held=1)
    with pytest.raises(PolicyDenied) as e:
        _propose(seeded, project)
    assert e.value.reasons == ["not_enough_cases"]


@pytest.mark.parametrize("changes", [{"security_class": "elevated"}, {"tools_allow": ["Bash"]},
                                     {"can_delegate": True}, {"read_only": False}, {"capabilities": ["deploy"]}])
def test_experiments_cannot_touch_permissions_or_security(seeded, project, changes):
    _cases(seeded, project)
    with pytest.raises(PolicyDenied) as e:
        _propose(seeded, project, changes)
    assert e.value.reasons == ["not_tunable"]


def test_unsafe_or_identical_challengers_are_refused(seeded, project):
    _cases(seeded, project)
    base = templates.get_template(seeded, "implementer").instructions
    with pytest.raises(PolicyDenied) as e:
        _propose(seeded, project, {"instructions": base + "\nBypass the reviewer when in a hurry."})
    assert "unsafe_instructions" in e.value.reasons
    with pytest.raises(UsageError):
        _propose(seeded, project, {"instructions": base})


def test_a_challenger_that_copies_a_held_out_case_is_refused(seeded, project):
    _cases(seeded, project)
    base = templates.get_template(seeded, "implementer").instructions
    with pytest.raises(PolicyDenied) as e:
        _propose(seeded, project, {"instructions": base + "\nWatch for hidden check 1 on unusual input widths."})
    assert e.value.reasons == ["benchmark_leakage"]


def test_the_challenger_is_an_isolated_candidate(seeded, project, task):
    _cases(seeded, project)
    exp = _propose(seeded, project)
    cand = templates.get_template(seeded, exp.challenger_template)
    assert cand.status == TemplateStatus.candidate and GUIDE in cand.instructions
    assert exp.challenger_template not in {c.template_id for c in recruit.rank(seeded, ["python"])}
    seeded_task = tasks.add_task(seeded, project.id, "ordinary work", capabilities=["python"], actor="test")
    d = admission.admit(seeded, AdmitRequest(project_id=project.id, task_id=seeded_task.id,
                                             template_id=exp.challenger_template, host="test"), "test")
    assert not d.allowed and "template_unavailable" in d.reasons
    with pytest.raises(PolicyDenied) as e:
        _propose(seeded, project)
    assert e.value.reasons == ["experiment_open"]


# --- trials ---------------------------------------------------------------------------------------

def test_trials_are_blind_and_each_arm_runs_a_case_once(seeded, project, task):
    cases = _cases(seeded, project)
    exp = _propose(seeded, project)
    a = improve.start_trial(seeded, exp.id, cases[0], "champion", "test", "test")
    b = improve.start_trial(seeded, exp.id, cases[0], "challenger", "test", "test")
    assert {a["label"], b["label"]} == {"A", "B"} and b["template_id"] == exp.challenger_template
    assert tasks.get_task(seeded, a["task_id"]).title.startswith(f"[trial {exp.id} ")
    assert all("arm" not in t for t in improve.trials_of(seeded, exp.id))
    with pytest.raises(PolicyDenied) as e:
        improve.start_trial(seeded, exp.id, cases[0], "champion", "test", "test")
    assert e.value.reasons == ["trial_exists"]
    with pytest.raises(UsageError):
        improve.start_trial(seeded, exp.id, cases[1], "both", "test", "test")


def test_cases_added_after_the_experiment_do_not_count(seeded, project, monkeypatch):
    _cases(seeded, project)
    exp = _propose(seeded, project)
    monkeypatch.setattr(improve, "now_iso", lambda: "2999-01-01T00:00:00Z")
    late = improve.add_case(seeded, project.id, "core", "late case", PASS, "representative", "test",
                            capabilities=["python"])
    with pytest.raises(PolicyDenied) as e:
        improve.start_trial(seeded, exp.id, late["id"], "champion", "test", "test")
    assert e.value.reasons == ["case_after_experiment"]


def test_grades_must_be_independent_and_cite_the_case_evidence(seeded, project, task):
    cases = _cases(seeded, project)
    exp = _propose(seeded, project)
    r = improve.start_trial(seeded, exp.id, cases[0], "challenger", "test", "test")
    improve.check_trial(seeded, r["trial_id"], "test")
    with pytest.raises(PolicyDenied):
        improve.check_trial(seeded, r["trial_id"], "test")
    same_arm = add_instance(seeded, project, task, "implementer")
    scores = {k: 90 for k in performance.WEIGHTS}
    t = improve._trial(seeded, r["trial_id"])
    e1 = performance.record_eval(seeded, r["instance_id"], same_arm, "coding", scores, [t["evidence_id"]],
                                 actor="test")
    with pytest.raises(PolicyDenied) as e:
        improve.score_trial(seeded, r["trial_id"], e1.id, "test")
    assert e.value.reasons == ["evaluator_not_independent"]
    other = add_instance(seeded, project, task)
    e2 = performance.record_eval(seeded, r["instance_id"], other, "coding", scores,
                                 [add_evidence(seeded, project.id)], actor="test")
    with pytest.raises(PolicyDenied) as e:
        improve.score_trial(seeded, r["trial_id"], e2.id, "test")
    assert e.value.reasons == ["evidence_not_from_case"]
    with pytest.raises(NotFound):
        improve.score_trial(seeded, r["trial_id"], "eval_missing", "test")


def test_an_abandoned_trial_counts_as_a_failure(seeded, project, task):
    cases = _cases(seeded, project)
    exp = _propose(seeded, project)
    r = improve.start_trial(seeded, exp.id, cases[0], "challenger", "test", "test")
    assert improve.evaluate(seeded, exp.id)["in_progress"] == [r["trial_id"]]
    seeded.execute("UPDATE agent_instances SET state='FAILED' WHERE id=?", (r["instance_id"],))
    _run(seeded, exp, cases[0], "champion", 70, add_instance(seeded, project, task))
    rep = improve.evaluate(seeded, exp.id)["representative"]
    assert rep["challenger_mean"] == 0.0 and rep["losses"] == 1


# --- deciding -------------------------------------------------------------------------------------

def test_decide_refuses_while_the_evidence_is_incomplete(seeded, project):
    _cases(seeded, project)
    exp = _propose(seeded, project)
    with pytest.raises(PolicyDenied) as e:
        improve.decide(seeded, exp.id, "test")
    assert set(e.value.reasons) == {"not_enough_trials", "not_enough_heldout_trials", "gate_not_passed",
                                    "not_enough_evaluators"}
    assert improve.get_experiment(seeded, exp.id).status == "trialing"


def test_a_failing_gate_blocks_promotion(seeded, project, task):
    cases = _cases(seeded, project)
    exp = _propose(seeded, project)
    _trial_all(seeded, project, task, exp, cases)
    improve.gate(seeded, exp.id, FAIL, "test")
    with pytest.raises(PolicyDenied) as e:
        improve.decide(seeded, exp.id, "test")
    assert e.value.reasons == ["gate_not_passed"]


def test_a_champion_changed_during_the_experiment_cannot_be_decided(seeded, project, task):
    cases = _cases(seeded, project)
    exp = _propose(seeded, project)
    _trial_all(seeded, project, task, exp, cases[1:])
    improve.gate(seeded, exp.id, PASS, "test")
    templates.add_template(seeded, templates.get_template(seeded, "implementer").model_copy(
        update={"description": "edited"}), "test")
    with pytest.raises(PolicyDenied) as e:
        improve.start_trial(seeded, exp.id, cases[0], "champion", "test", "test")
    assert e.value.reasons == ["champion_changed"]
    with pytest.raises(PolicyDenied) as e:
        improve.decide(seeded, exp.id, "test")
    assert "champion_changed" in e.value.reasons


def test_lookups_and_closed_experiments_are_refused(seeded, project, task):
    for fn, arg in ((improve._case, "case_x"), (improve.get_experiment, "exp_x"), (improve._trial, "trl_x"),
                    (improve.get_retro, "retro_x")):
        with pytest.raises(NotFound):
            fn(seeded, arg)
    cases = _cases(seeded, project)
    other = improve.add_case(seeded, project.id, "other", "another suite case", PASS, "representative", "test")
    exp = _propose(seeded, project)
    with pytest.raises(PolicyDenied) as e:
        improve.start_trial(seeded, exp.id, other["id"], "champion", "test", "test")
    assert e.value.reasons == ["case_not_in_suite"]
    improve.abandon(seeded, exp.id, "test", "not needed")
    with pytest.raises(PolicyDenied) as e:
        improve.start_trial(seeded, exp.id, cases[0], "champion", "test", "test")
    assert e.value.reasons == ["experiment_closed"]


def test_hypotheses_and_champions_must_be_sound(seeded, project):
    _cases(seeded, project)
    base = templates.get_template(seeded, "implementer").instructions
    with pytest.raises(UsageError):
        improve.propose_template(seeded, project.id, "implementer", {"instructions": base + "\nx"}, " ", "core",
                                 "test")
    with pytest.raises(UsageError):
        improve.propose_policy(seeded, project.id, "recruit.w_match", 0.6, "", "core", "test")
    templates.set_status(seeded, "implementer", TemplateStatus.suspended, "test", "weak")
    with pytest.raises(PolicyDenied) as e:
        _propose(seeded, project)
    assert e.value.reasons == ["champion_not_active"]


def test_a_refused_trial_leaves_no_trial_behind(seeded, project, task):
    cases = _cases(seeded, project)
    exp = _propose(seeded, project)
    for _ in range(4):
        add_instance(seeded, project, task)
    r = improve.start_trial(seeded, exp.id, cases[0], "champion", "test", "test")
    assert r["status"] == "denied" and "max_concurrent" in r["reasons"] and r["trial_id"] is None
    assert improve.trials_of(seeded, exp.id) == []
    assert tasks.get_task(seeded, r["task_id"]).state == tasks.TaskState.cancelled


def test_a_trial_is_scored_once_and_only_for_its_worker(seeded, project, task):
    cases = _cases(seeded, project)
    exp = _propose(seeded, project)
    r = _run(seeded, exp, cases[0], "champion", 70, add_instance(seeded, project, task))
    with pytest.raises(PolicyDenied) as e:
        improve.score_trial(seeded, r["trial_id"], improve._trial(seeded, r["trial_id"])["evaluation_id"], "test")
    assert e.value.reasons == ["already_scored"]
    r2 = improve.start_trial(seeded, exp.id, cases[0], "challenger", "test", "test")
    ev2 = improve.check_trial(seeded, r2["trial_id"], "test")
    with pytest.raises(PolicyDenied) as e:
        improve.decide(seeded, exp.id, "test")
    assert "trials_in_progress" in e.value.reasons
    other = add_instance(seeded, project, task)
    wrong = performance.record_eval(seeded, r["instance_id"], other, "coding",
                                    {k: 90 for k in performance.WEIGHTS}, [ev2.id], actor="test")
    with pytest.raises(PolicyDenied) as e:
        improve.score_trial(seeded, r2["trial_id"], wrong.id, "test")
    assert "evaluation_not_for_trial" in e.value.reasons


def test_a_better_challenger_is_promoted_into_the_champion(seeded, project, task):
    cases = _cases(seeded, project)
    exp = _propose(seeded, project)
    _trial_all(seeded, project, task, exp, cases, champ=70, chal=80)
    improve.gate(seeded, exp.id, PASS, "test")
    out = improve.decide(seeded, exp.id, "test")
    assert out["status"] == "promoted" and out["result"]["representative"]["delta"] == pytest.approx(10)
    champ = templates.get_template(seeded, "implementer")
    assert champ.version == 2 and GUIDE in champ.instructions and champ.status == TemplateStatus.active
    assert champ.security_class == "standard" and champ.tools_allow == templates.get_template(
        seeded, "implementer", 1).tools_allow
    assert out["monitor"]["previous_version"] == 1 and out["monitor"]["baseline_mean"] == pytest.approx(70)
    learned = memory.search(seeded, project.id, "Validated improvement", validated_only=True)
    assert learned and learned[0].scope == "org" and learned[0].layer == memory.Layer.procedural
    # the candidate is finished: it cannot work outside a running experiment
    t = tasks.add_task(seeded, project.id, "after", capabilities=["python"], actor="test")
    d = admission.admit(seeded, AdmitRequest(project_id=project.id, task_id=t.id,
                                             template_id=exp.challenger_template, host="test"), "test")
    assert not d.allowed


@pytest.mark.parametrize(("chal", "held", "why"), [(65, None, "below the"), (80, 60, "held-out"),
                                                   (71, None, "margin")])
def test_a_weaker_challenger_is_rejected_and_remembered(seeded, project, task, chal, held, why):
    cases = _cases(seeded, project)
    exp = _propose(seeded, project)
    _trial_all(seeded, project, task, exp, cases, champ=70, chal=chal, held_chal=held)
    improve.gate(seeded, exp.id, PASS, "test")
    out = improve.decide(seeded, exp.id, "test")
    assert out["status"] == "rejected" and any(why in w for w in out["result"]["why"])
    assert templates.get_template(seeded, "implementer").version == 1
    assert memory.search(seeded, project.id, "Rejected change")


def test_a_flagged_trial_blocks_promotion(seeded, project, task):
    cases = _cases(seeded, project)
    exp = _propose(seeded, project)
    a, b = add_instance(seeded, project, task), add_instance(seeded, project, task)
    for i, cid in enumerate(cases):
        _run(seeded, exp, cid, "champion", 70, a if i % 2 else b)
        last = i == len(cases) - 1  # a flag quarantines the challenger, so no later trial could start
        _run(seeded, exp, cid, "challenger", 90, a if i % 2 else b, flags=["integrity_violation"] if last else None)
    improve.gate(seeded, exp.id, PASS, "test")
    out = improve.decide(seeded, exp.id, "test")
    assert out["status"] == "rejected" and any("flagged" in w for w in out["result"]["why"])


def test_used_held_out_cases_no_longer_count_as_held_out(seeded, project, task):
    cases = _cases(seeded, project)
    exp = _propose(seeded, project)
    _trial_all(seeded, project, task, exp, cases)
    improve.abandon(seeded, exp.id, "test", "superseded")
    with pytest.raises(PolicyDenied) as e:
        _propose(seeded, project)
    assert e.value.reasons == ["not_enough_cases"]


# --- monitoring and rollback ----------------------------------------------------------------------

def _promoted(seeded, project, task):
    cases = _cases(seeded, project)
    exp = _propose(seeded, project)
    _trial_all(seeded, project, task, exp, cases)
    improve.gate(seeded, exp.id, PASS, "test")
    improve.decide(seeded, exp.id, "test")
    return exp


def test_a_regression_after_promotion_is_rolled_back(seeded, project, task):
    exp = _promoted(seeded, project, task)
    _grade_version(seeded, project, task, 2, 70, n=4)
    assert improve.monitor(seeded, "test")[0]["status"] == "monitoring"
    _grade_version(seeded, project, task, 2, 20, n=2)
    out = improve.monitor(seeded, "test")
    assert out[0]["status"] == "rolled_back"
    restored = templates.get_template(seeded, "implementer")
    assert restored.version == 3 and restored.instructions == templates.get_template(seeded, "implementer", 1).instructions
    assert improve.get_experiment(seeded, exp.id).status == "rolled_back"
    assert memory.search(seeded, project.id, "Rolled back")


def test_a_holding_improvement_is_adopted(seeded, project, task):
    exp = _promoted(seeded, project, task)
    _grade_version(seeded, project, task, 2, 75)
    assert improve.monitor(seeded, "test")[0]["status"] == "adopted"
    assert improve.get_experiment(seeded, exp.id).status == "adopted"


def test_a_champion_changed_by_hand_supersedes_the_monitor(seeded, project, task):
    exp = _promoted(seeded, project, task)
    templates.add_template(seeded, templates.get_template(seeded, "implementer").model_copy(
        update={"description": "edited"}), "test")
    assert improve.monitor(seeded, "test")[0]["status"] == "superseded"
    assert improve.get_experiment(seeded, exp.id).status == "superseded"


# --- policy experiments ---------------------------------------------------------------------------

def test_policy_experiments_stay_in_bounds(seeded, project):
    _cases(seeded, project)
    with pytest.raises(PolicyDenied) as e:
        improve.propose_policy(seeded, project.id, "recruit.w_match", 0.95, "more", "core", "test")
    assert e.value.reasons == ["out_of_bounds"]
    with pytest.raises(PolicyDenied) as e:
        improve.propose_policy(seeded, project.id, "governor.max_concurrent", 9, "more", "core", "test")
    assert e.value.reasons == ["not_tunable"]
    with pytest.raises(UsageError):
        improve.propose_policy(seeded, project.id, "recruit.w_match", 0.45, "same", "core", "test")


def test_a_better_policy_is_promoted_then_monitored(seeded, project, task):
    cases = _cases(seeded, project)
    exp = improve.propose_policy(seeded, project.id, "recruit.w_match", 0.6, "match matters more", "core", "test")
    _trial_all(seeded, project, task, exp, cases, champ=70, chal=80)
    improve.gate(seeded, exp.id, PASS, "test")
    assert improve.decide(seeded, exp.id, "test")["status"] == "promoted"
    assert get_setting(seeded, "policy.recruit.w_match") == 0.6
    assert recruit._weights(seeded)["match"] == 0.6
    _grade_version(seeded, project, task, 1, 10)
    assert improve.monitor(seeded, "test")[0]["status"] == "rolled_back"
    assert get_setting(seeded, "policy.recruit.w_match") == 0.45


# --- retrospectives -------------------------------------------------------------------------------

def test_retro_diagnoses_weaknesses_and_proposes_a_testable_change(seeded, project, task):
    _grade_version(seeded, project, task, 1, 60, n=3)
    r = improve.retro(seeded, project.id, "test")
    kinds = {(w["kind"], w.get("subscore")) for w in r["weaknesses"]}
    assert ("template_subscore", "quality") in kinds
    assert r["hypotheses"][0]["target"] == "implementer"
    assert improve.get_retro(seeded, r["id"])["weaknesses"] == r["weaknesses"]
    _cases(seeded, project)
    exp = improve.propose_from_retro(seeded, r["id"], 0, "core", "test")
    assert improve.GUIDANCE["quality"] in templates.get_template(seeded, exp.challenger_template).instructions
    with pytest.raises(UsageError):
        improve.propose_from_retro(seeded, r["id"], 9, "core", "test")
    # the same change is not proposed twice
    assert not [h for h in improve.retro(seeded, project.id, "test")["hypotheses"] if h["target"] == "implementer"]


def test_recurring_capability_mismatches_suggest_a_recruitment_policy(seeded, project):
    t = tasks.add_task(seeded, project.id, "py", capabilities=["python"], actor="test")
    for _ in range(3):
        admission.admit(seeded, AdmitRequest(project_id=project.id, task_id=t.id, template_id="researcher",
                                             host="test"), "test")
    r = improve.retro(seeded, project.id, "test")
    assert {"kind": "admission_reason", "reason": "capability_mismatch", "count": 3} in r["weaknesses"]
    h = r["hypotheses"][0]
    assert (h["kind"], h["target"], h["value"]) == ("policy", "recruit.w_match", 0.55)
    _cases(seeded, project)
    exp = improve.propose_from_retro(seeded, r["id"], 0, "core", "test")
    assert (exp.kind, exp.challenger) == ("policy", {"value": 0.55})


def test_retro_sees_failing_evidence_and_failing_capabilities(seeded, project, task):
    ev = add_instance(seeded, project, task)
    for _ in range(3):
        iid = add_instance(seeded, project, task, "implementer", state="COMPLETED")
        performance.record_eval(seeded, iid, ev, "coding", {k: 90 for k in performance.WEIGHTS},
                                [add_evidence(seeded, project.id, exit_code=1)], actor="test")
    for i in range(2):
        t = tasks.add_task(seeded, project.id, f"broken {i}", capabilities=["python"], actor="test")
        tasks.set_state(seeded, t.id, tasks.TaskState.running, "test")
        tasks.set_state(seeded, t.id, tasks.TaskState.failed, "test")
    weaknesses = improve.diagnose(seeded, project.id)
    assert {"kind": "evidence_failures", "template_id": "implementer", "failed": 3, "evaluations": 3} in weaknesses
    assert {"kind": "task_failures", "capability": "python", "count": 2} in weaknesses
    hyp = improve.hypotheses(seeded, weaknesses)
    assert improve.GUIDANCE["reliability"] in hyp[0]["changes"]["instructions"]
    r = improve.retro(seeded, project.id, "test", task_id=task.id)
    assert r["unsuccessful"] and r["unsuccessful"][0]["evidence_passed"] is False


def test_accepting_a_task_runs_a_retrospective(seeded, project):
    t = tasks.add_task(seeded, project.id, "ship", capabilities=["python"], actor="test")
    worker = add_instance(seeded, project, t, "implementer")
    tasks.set_state(seeded, t.id, tasks.TaskState.running, "test")
    tasks.set_state(seeded, t.id, tasks.TaskState.done, "test")
    ev = performance.record_eval(seeded, worker, add_instance(seeded, project, t), "coding",
                                 {k: 92 for k in performance.WEIGHTS}, [add_evidence(seeded, project.id)],
                                 actor="test")
    out = boss.accept_task(seeded, t.id, ev.id, "test")
    retro = improve.get_retro(seeded, out["retrospective"]["id"])
    assert retro["scope"] == "task" and retro["successful"][0]["template_id"] == "implementer"


def test_a_retro_cannot_reach_another_projects_task(seeded, project, tmp_path):
    from agentos import projects

    other_repo = tmp_path / "other"
    other_repo.mkdir()
    (other_repo / ".git").mkdir()
    other = projects.activate(seeded, other_repo, actor="test")
    t = tasks.add_task(seeded, other.id, "theirs", actor="test")
    with pytest.raises(PolicyDenied):
        improve.retro(seeded, project.id, "test", task_id=t.id)
