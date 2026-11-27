"""Organisational intelligence, each feature checked against a ledger with a known, planted answer:
the detector must find what was planted and nothing that was not."""

import itertools
import json

import pytest

from agentos import audit, boss, governor, intel, memory, performance, projects, tasks, templates
from agentos.errors import NotFound, PolicyDenied, UsageError
from agentos.memory import Layer
from agentos.templates import AgentTemplate
from agentos.util import new_id, now_iso
from tests.conftest import make_repo

ALL = list(performance.WEIGHTS)


def _worker(conn, project, task_id, template="implementer", state="RUNNING", parent=None):
    iid, ts = new_id("ag"), now_iso()
    conn.execute(
        "INSERT INTO agent_instances(id, template_id, template_version, project_id, task_id, parent_id, depth,"
        " host, state, created_at, updated_at) VALUES (?, ?, 1, ?, ?, ?, 0, 'test', ?, ?, ?)",
        (iid, template, project.id, task_id, parent, state, ts, ts))
    return iid


def _evidence(conn, project_id, argv=("pytest", "-q"), code=0, tail="3 passed", timed_out=0):
    eid, ts = new_id("evd"), now_iso()
    conn.execute(
        "INSERT INTO evidence(id, project_id, command, cwd, exit_code, timed_out, stdout_sha256, stderr_sha256,"
        " output_tail, git_head, started_at, finished_at, duration_ms, actor)"
        " VALUES (?, ?, ?, '.', ?, ?, 'x', 'x', ?, NULL, ?, ?, 1, 'test')",
        (eid, project_id, json.dumps(list(argv)), code, timed_out, tail, ts, ts))
    return eid


def _grade(conn, project, iid, value, evidence=None, evaluator=None, scores=None):
    ev = evaluator or _worker(conn, project, conn.execute("SELECT task_id FROM agent_instances WHERE id=?",
                                                          (iid,)).fetchone()[0], "reviewer")
    return performance.record_eval(conn, iid, ev, "coding", scores or {k: value for k in ALL},
                                   [evidence or _evidence(conn, project.id)], actor="test")


def _task(conn, project, title="work", caps=("implementation",), risk="low", effort=1, state=None):
    t = tasks.add_task(conn, project.id, title, capabilities=list(caps), risk=risk, actor="test")
    conn.execute("UPDATE tasks SET effort=? WHERE id=?", (effort, t.id))
    for s in {"running": ["running"], "done": ["running", "done"], "failed": ["running", "failed"]}.get(state, []):
        tasks.set_state(conn, t.id, s, "test")
    return t


# --- predictive staffing ---

def test_staffing_finds_the_waves_the_peak_and_the_gaps(seeded, project):
    a, b, c = (_task(seeded, project, f"part {i}") for i in range(3))
    review = _task(seeded, project, "review", caps=("review",))
    for t in (a, b, c):
        tasks.add_dependency(seeded, review.id, t.id, "test")
    _task(seeded, project, "exotic", caps=("quantum",))
    r = intel.staffing(seeded, project.id)
    assert (r["open_tasks"], r["waves"], r["peak_parallel"]) == (5, 2, 4)
    caps = {x["capability"]: x for x in r["by_capability"]}
    assert caps["implementation"]["peak_parallel"] == 3 and caps["implementation"]["template_id"] == "implementer"
    assert caps["review"]["peak_parallel"] == 1 and caps["review"]["template_id"] == "reviewer"
    assert r["capability_gaps"] == ["quantum"] and caps["quantum"]["action"] == "agentos factory propose --cap quantum"
    assert r["recommended_workers"] == 4 and not r["limited_by_max_concurrent"]
    _worker(seeded, project, a.id)
    r = intel.staffing(seeded, project.id)
    assert r["already_working"] == 1 and r["to_recruit"] == 3
    governor.set_limit(seeded, "max_concurrent", 2, "test")
    r = intel.staffing(seeded, project.id)
    assert r["recommended_workers"] == 2 and r["limited_by_max_concurrent"]


def test_staffing_learns_workers_per_task_from_finished_work(seeded, project):
    for i in range(3):
        t = _task(seeded, project, f"done {i}", state="done")
        _worker(seeded, project, t.id, state="COMPLETED")
        _worker(seeded, project, t.id, "reviewer", state="COMPLETED")
    _task(seeded, project, "open")
    r = intel.staffing(seeded, project.id)
    assert r["history_basis"] == "project" and r["workers_per_task"] == 2.0 and r["recommended_workers"] == 2
    assert intel.staffing(seeded, project.id, objective_id="obj_none")["open_tasks"] == 0


# --- model routing ---

def test_routing_follows_risk_effort_and_record(seeded, project):
    assert intel.route(seeded, _task(seeded, project).id)["tier"] == "small"
    r = intel.route(seeded, _task(seeded, project, risk="high").id, "implementer")
    assert r["tier"] == "large" and r["reasoning_hint"] == "high"
    assert intel.route(seeded, _task(seeded, project, risk="medium", effort=5).id)["tier"] == "large"
    assert r["paid_spend_allowed"] is False and "cap 0" in r["note"]


def test_a_strong_record_lowers_medium_risk_but_never_critical(seeded, project):
    done = _task(seeded, project, "past", state="done")
    for _ in range(3):
        _grade(seeded, project, _worker(seeded, project, done.id), 92)
    r = intel.route(seeded, _task(seeded, project, risk="medium").id)
    assert r["tier"] == "small" and "this project" in r["reasons"][-1]
    assert intel.route(seeded, _task(seeded, project, risk="critical").id, "implementer")["tier"] == "large"


def test_a_weak_record_raises_the_tier(seeded, project):
    done = _task(seeded, project, "past", state="done")
    for _ in range(3):
        _grade(seeded, project, _worker(seeded, project, done.id), 30)
    r = intel.route(seeded, _task(seeded, project).id)
    assert r["tier"] == "medium" and "fails 100%" in r["reasons"][-1]
    assert "not enough history" in intel.route(seeded, _task(seeded, project, caps=("research",)).id)["reasons"][-1]
    nobody = intel.route(seeded, _task(seeded, project, caps=("quantum",)).id)
    assert nobody["template_id"] is None and nobody["tier"] == "small"


# --- context optimisation ---

def test_context_pack_puts_validated_and_failures_first_and_respects_the_budget(seeded, project):
    t = _task(seeded, project, "export csv report", caps=("csv",))
    plain = memory.add(seeded, project.id, Layer.episodic, "csv export used semicolons once", "t", "t")
    fail = memory.add(seeded, project.id, Layer.failure, "csv export broke on unicode names", "t", "t")
    valid = memory.add(seeded, project.id, Layer.semantic, "csv export must be utf-8 with BOM", "t", "t",
                       validated=True)
    dup = memory.add(seeded, project.id, Layer.semantic, "CSV export used semicolons   once", "t", "t")
    long = memory.add(seeded, project.id, Layer.episodic, "csv " + "x" * 400, "t", "t")
    r = intel.context_pack(seeded, t.id, budget_tokens=60)
    assert [x["id"] for x in r["included"]][:2] == [valid.id, fail.id]
    reasons = {x["id"]: x["reason"] for x in r["excluded"]}
    assert reasons[long.id] == "over_budget"
    assert reasons.get(dup.id, reasons.get(plain.id)) == "duplicate"
    assert r["used_tokens_est"] <= 60 and r["left_out_tokens_est"] > 100 and r["duplicate_tokens_est"] > 0
    with pytest.raises(UsageError):
        intel.context_pack(seeded, t.id, budget_tokens=10)


# --- skills from proven commands ---

def test_a_command_proven_in_three_graded_tasks_becomes_a_skill(seeded, project, home):
    proven = ("python", "-m", "pytest", "-q")
    for i in range(3):
        t = _task(seeded, project, f"t{i}", state="done")
        _grade(seeded, project, _worker(seeded, project, t.id), 85, _evidence(seeded, project.id, proven))
    two = None
    for i in range(2):
        t = _task(seeded, project, f"u{i}", state="done")
        two = _evidence(seeded, project.id, ("ruff", "check"))
        _grade(seeded, project, _worker(seeded, project, t.id), 85, two)
    for i in range(3):  # graded well, but the command fails as often as it passes
        t = _task(seeded, project, f"v{i}", state="done")
        _grade(seeded, project, _worker(seeded, project, t.id), 85, _evidence(seeded, project.id, ("flaky",)))
        _evidence(seeded, project.id, ("flaky",), code=1)
    found = intel.skill_candidates(seeded, project.id)
    assert [c["command"] for c in found] == ["python -m pytest -q"] and found[0]["tasks"] == 3
    r = intel.create_skill(seeded, project.id, found[0]["evidence"][0], "test")
    path = home / "skills" / project.id / "python-m-pytest-q" / "SKILL.md"
    assert r["path"] == str(path) and "agentos evidence run -- python -m pytest -q" in path.read_text("utf-8")
    rec = memory.inspect(seeded, r["memory_id"])
    assert rec.layer == Layer.procedural and rec.validated and "skill" in rec.tags
    assert audit.list_events(seeded, kind="intel.skill_created")
    with pytest.raises(PolicyDenied) as e:
        intel.create_skill(seeded, project.id, two, "test")
    assert e.value.reasons == ["not_enough_evidence"]
    with pytest.raises(NotFound):
        intel.create_skill(seeded, project.id, "evd_missing", "test")
    assert intel.create_skill(seeded, project.id, found[0]["evidence"][0], "test")["path"] == str(path)  # again
    path.write_text("someone else's skill", encoding="utf-8")
    with pytest.raises(PolicyDenied) as e:
        intel.create_skill(seeded, project.id, found[0]["evidence"][0], "test")
    assert e.value.reasons == ["skill_exists"]
    odd = _evidence(seeded, project.id, ("echo", "`x`"))
    with pytest.raises(PolicyDenied) as e:
        intel.create_skill(seeded, project.id, odd, "test")
    assert e.value.reasons == ["unsafe_command"]


def test_skills_ignore_evidence_from_another_project(seeded, project, tmp_path):
    other = projects.activate(seeded, make_repo(tmp_path / "other"), actor="t")
    foreign = _evidence(seeded, other.id, ("make", "check"))
    for i in range(3):
        t = _task(seeded, project, f"t{i}", state="done")
        w = _worker(seeded, project, t.id)
        ev = _grade(seeded, project, w, 85)
        seeded.execute("UPDATE evaluations SET evidence=? WHERE id=?", (json.dumps([foreign]), ev.id))
    assert intel.skill_candidates(seeded, project.id) == []


# --- organisational optimisation ---

def test_org_review_finds_idle_overlapping_single_point_overloaded_and_idle_departments(seeded, project):
    templates.add_template(seeded, AgentTemplate(id="impl-two", name="x", role="implementer", department="eng",
                                                 description="x", capabilities=["python", "implementation",
                                                                                "testing"], instructions="x"), "t")
    _worker(seeded, project, _task(seeded, project).id)  # implementer was recruited just now
    for i in range(3):
        _task(seeded, project, f"r{i}", caps=("research",))
    for i in range(10):
        _task(seeded, project, f"p{i}", caps=("planning",))
    obj = boss.create_objective(seeded, project.id, "ship", acceptance=["tests pass"], actor="t")
    seeded.execute("INSERT INTO departments(id, objective_id, function, created_at) VALUES ('dep_1', ?, 'qa', ?)",
                   (obj.id, now_iso()))
    r = intel.org_review(seeded, project.id)
    kinds = {(f["kind"], f["subject"]) for f in r["findings"]}
    assert ("overlapping_templates", "impl-two+implementer") in kinds
    assert ("single_point_of_failure", "research") in kinds
    assert ("overloaded_capability", "planning") in kinds
    assert ("idle_department", f"{obj.id}/qa") in kinds
    idle = {s for k, s in kinds if k == "idle_template"}
    assert "implementer" not in idle and "reviewer" in idle


def test_org_review_reports_nothing_structural_for_a_balanced_org(seeded, project):
    for tid, cap in (("implementer", "testing"), ("reviewer", "testing"), ("planner", "planning"),
                     ("lead", "planning"), ("researcher", "analysis"), ("recovery", "debugging")):
        _worker(seeded, project, _task(seeded, project, caps=(cap,)).id, tid)
    assert intel.org_review(seeded, project.id)["findings"] == []


# --- failure patterns ---

def test_signature_ignores_paths_numbers_and_quoted_values():
    a = intel.signature("collected 3 items\nE  AssertionError: 'abc' != 'abd' at C:\\src\\a.py:12\n1 failed")
    b = intel.signature("collected 9 items\nE  AssertionError: 'q' != 'r' at /home/u/b.py:90\n2 failed")
    assert a == b
    assert intel.signature("", timed_out=True) == "timed out" and intel.signature("") == "(no output)"
    # an apostrophe inside a word is not a quote, so the words between two of them survive
    assert "connect to server" in intel.signature("error: can't connect to server, don't retry")


def test_waves_handle_long_chains_and_cycles(seeded, project):
    chain = [_task(seeded, project, f"c{i}") for i in range(1500)]
    for prev, nxt in itertools.pairwise(chain):
        seeded.execute("INSERT INTO task_deps VALUES (?, ?)", (nxt.id, prev.id))
    assert len(intel._layers(intel._open_tasks(seeded, project.id))) == 1500
    seeded.execute("INSERT INTO task_deps VALUES (?, ?)", (chain[0].id, chain[-1].id))  # hand-made cycle
    waves = intel._layers(intel._open_tasks(seeded, project.id))
    assert sum(len(w) for w in waves) == 1500


def test_failure_patterns_find_what_was_planted_and_record_it_once(seeded, project):
    for n in (3, 7, 11):
        _evidence(seeded, project.id, code=1, tail=f"FAILED test_x.py::t{n} - KeyError: 'k{n}'")
    _evidence(seeded, project.id, code=2, tail="error: something unique happened")
    for _ in range(2):
        _evidence(seeded, project.id, ("slow",), code=-1, tail="", timed_out=1)
    done = _task(seeded, project, state="done")
    low = {k: 70 for k in ALL} | {"security_compliance": 5, "quality": 30, "accuracy": 30, "reliability": 30}
    for _ in range(2):
        _grade(seeded, project, _worker(seeded, project, done.id), 0, scores=low)
    for i in range(2):
        _task(seeded, project, f"f{i}", caps=("parsing",), state="failed")
    seeded.execute("INSERT INTO evaluations(id, instance_id, template_id, evaluator_id, category, scores, weighted,"
                   " evidence, created_at) SELECT 'ev_empty', id, template_id, 'x', 'c', '{}', 0, '[]', created_at"
                   " FROM agent_instances LIMIT 1")  # a malformed row is skipped, not a crash
    r = intel.failure_patterns(seeded, project.id)
    got = {(p["kind"], p.get("signature") or p.get("dimension") or p.get("capability")): p["count"]
           for p in r["patterns"]}
    sig = intel.signature("FAILED test_x.py::t3 - KeyError: 'k3'")
    assert got == {("error", sig): 3, ("error", "timed out"): 2, ("weak_dimension", "security_compliance"): 2,
                   ("failing_capability", "parsing"): 2}
    first = intel.failure_patterns(seeded, project.id, actor="test", record=True)["recorded"]
    again = intel.failure_patterns(seeded, project.id, actor="test", record=True)["recorded"]
    assert len(first) == 4 and first == again
    assert all(memory.inspect(seeded, m).layer == Layer.failure for m in first)


# --- competitive evaluation ---

def test_compete_picks_the_independent_winner_and_disqualifies_the_rest(seeded, project):
    t = _task(seeded, project, state="running")
    a, b, c = (_worker(seeded, project, t.id) for _ in range(3))
    judge = _worker(seeded, project, t.id, "reviewer")
    _grade(seeded, project, a, 90, evaluator=judge)
    _grade(seeded, project, b, 80, evaluator=judge)
    _grade(seeded, project, b, 100, evaluator=a)  # a competitor's grade does not count
    _grade(seeded, project, c, 99, _evidence(seeded, project.id, code=1), evaluator=judge)
    silent = _worker(seeded, project, t.id)  # competes but was never graded
    _grade(seeded, project, a, 10, evaluator=silent)  # so its grade of a rival is not independent
    r = intel.compete(seeded, t.id)
    assert r["verdict"] == "winner" and r["winner"] == a and r["margin"] == 10
    by = {s["instance_id"]: s for s in r["solutions"]}
    assert by[b]["discarded"][0]["reason"] == "evaluator_is_competitor" and by[b]["mean"] == 80
    assert by[c]["disqualified"][0].startswith("failing_evidence:")
    assert by[silent]["disqualified"] == ["no_independent_evaluation"] and by[a]["mean"] == 90
    assert intel.compete(seeded, t.id, min_margin=20)["verdict"] == "no_clear_winner"


def test_compete_with_one_or_no_eligible_solution(seeded, project):
    t = _task(seeded, project, state="running")
    a = _worker(seeded, project, t.id)
    assert intel.compete(seeded, t.id)["verdict"] == "no_eligible_solution"
    _grade(seeded, project, a, 70)
    r = intel.compete(seeded, t.id)
    assert r["verdict"] == "only_one_eligible" and r["winner"] == a


# --- independent governance ---

def test_governance_passes_on_a_clean_ledger(seeded, project):
    t = _task(seeded, project, state="done")
    _grade(seeded, project, _worker(seeded, project, t.id, state="COMPLETED"), 90)
    r = intel.governance_check(seeded)
    assert r["ok"] and {c["name"] for c in r["checks"]} >= {"audit_chain", "evaluator_independence",
                                                            "gated_promotions", "paid_spend_cap", "concurrency"}


def test_governance_catches_each_planted_violation(seeded, project):
    t = _task(seeded, project, state="done")
    w = _worker(seeded, project, t.id, state="COMPLETED")
    ts = now_iso()
    bad_ev = _evidence(seeded, project.id, code=1)
    seeded.execute("INSERT INTO evaluations(id, instance_id, template_id, evaluator_id, category, scores, weighted,"
                   " evidence, created_at) VALUES ('ev_self', ?, 'implementer', ?, 'coding', '{}', 90, ?, ?)",
                   (w, w, json.dumps([bad_ev]), ts))
    seeded.execute("INSERT INTO task_acceptances VALUES (?, 'ev_self', ?, ?, 'x')", (t.id, bad_ev, ts))
    seeded.execute("INSERT INTO experiments(id, project_id, kind, target, suite, hypothesis, champion, challenger,"
                   " status, created_at, actor) VALUES ('exp_1', ?, 'template', 'x', 's', 'h', '{}', '{}',"
                   " 'promoted', ?, 'x')", (project.id, ts))
    seeded.execute("INSERT INTO reservations(id, scope, scope_id, kind, amount, holder, state, created_at)"
                   " VALUES ('r:global', 'global', '*', 'usd', 5, 'x', 'charged', ?)", (ts,))
    for _ in range(5):
        _worker(seeded, project, t.id)
    seeded.execute("INSERT INTO agent_templates VALUES ('ghost', 1, 'candidate', '{}', ?)", (ts,))
    _worker(seeded, project, t.id, "ghost", state="COMPLETED")
    seeded.execute("INSERT INTO memory(id, project_id, scope, layer, content, content_hash, source, author,"
                   " confidence, validated, created_at) VALUES ('mem_x', ?, 'org', 'semantic', 'x', 'h', 's', 'a',"
                   " 0.5, 0, ?)", (project.id, ts))
    seeded.execute("UPDATE events SET payload='{}' WHERE seq=2")
    r = intel.governance_check(seeded)
    failed = {c["name"] for c in r["checks"] if not c["ok"]}
    assert not r["ok"] and failed == {"audit_chain", "evaluator_independence", "evidence_backed_acceptance",
                                      "gated_promotions", "paid_spend_cap", "concurrency", "candidates_isolated",
                                      "org_memory_validated"}


# --- resource forecasting ---

def test_forecast_needs_history(seeded, project):
    _task(seeded, project)
    r = intel.forecast(seeded, project.id)
    assert r["projected"] is None and r["history_tasks"] == 0


def test_forecast_scales_finished_cost_to_the_remaining_effort_and_warns(seeded, project, owner):
    for i in range(3):
        t = _task(seeded, project, f"d{i}", effort=2, state="done")
        w = _worker(seeded, project, t.id)
        _worker(seeded, project, t.id, "reviewer", state="COMPLETED")
        governor.record_usage(seeded, w, "tokens_est", 1000, "test")
    for i in range(2):
        _task(seeded, project, f"o{i}", effort=3)
    governor.set_budget(seeded, "project", project.id, "tokens_est", 5000, "test", owner)
    r = intel.forecast(seeded, project.id)
    assert r["remaining_effort"] == 6 and r["per_effort_unit"] == {"agent_runs": 1.0, "tokens_est": 500.0}
    assert r["projected"]["agent_runs"] == 6 and r["projected"]["tokens_est"] == 3000 and r["projected"]["usd"] == 0
    assert r["warnings"] == [{"scope": "project", "kind": "tokens_est", "projected": 3000, "remaining": 2000.0,
                              "action": "re-plan the work, or ask the owner to raise the budget"}]


# --- project profile ---

def test_project_profile_summarises_this_project_only(seeded, project, tmp_path):
    for state in ("done", "done", "failed"):
        t = _task(seeded, project, state=state)
        _grade(seeded, project, _worker(seeded, project, t.id), 80)
    other = projects.activate(seeded, make_repo(tmp_path / "other"), actor="t")
    tasks.add_task(seeded, other.id, "elsewhere", actor="t")
    r = intel.project_profile(seeded, project.id)
    assert r["tasks"] == {"done": 2, "failed": 1} and r["success_rate"] == 0.667
    assert r["best_by_capability"]["implementation"]["template_id"] == "implementer"


# --- cross-project lessons ---

def test_a_lesson_is_shared_only_after_two_projects_validate_it(seeded, project, tmp_path):
    other = projects.activate(seeded, make_repo(tmp_path / "other"), actor="t")
    text = "Pin the parser version; minor releases change the output."
    a = memory.add(seeded, project.id, Layer.semantic, text, "t", "t", validated=True)
    solo = memory.add(seeded, project.id, Layer.semantic, "only here", "t", "t", validated=True)
    unvalidated = memory.add(seeded, project.id, Layer.semantic, "a hunch", "t", "t")
    local = memory.add(seeded, project.id, Layer.project, "project note", "t", "t", validated=True)
    with pytest.raises(PolicyDenied) as e:
        intel.share_lesson(seeded, a.id, "t")
    assert e.value.reasons == ["not_confirmed_elsewhere"]
    memory.add(seeded, other.id, Layer.semantic, "pin the parser version;  minor releases change the output.", "t",
               "t", validated=True)
    found = intel.lessons(seeded)
    assert len(found) == 1 and found[0]["projects"] == sorted([project.id, other.id])
    r = intel.share_lesson(seeded, a.id, "t")
    org = memory.inspect(seeded, r["memory_id"])
    assert org.scope == "org" and org.validated
    assert org.id in {m.id for m in memory.search(seeded, other.id, "parser")}
    assert intel.lessons(seeded) == []
    for rec, reason in ((solo, "not_confirmed_elsewhere"), (unvalidated, "not_validated"), (local, "org_layer"),
                        (org, "not_a_project_record")):
        with pytest.raises(PolicyDenied) as e:
            intel.share_lesson(seeded, rec.id, "t")
        assert e.value.reasons == [reason]


def test_a_skill_file_that_cannot_be_moved_leaves_no_record(seeded, project, monkeypatch):
    from pathlib import Path

    for i in range(3):
        t = _task(seeded, project, f"t{i}", state="done")
        ev = _evidence(seeded, project.id, ("make", "test"))
        _grade(seeded, project, _worker(seeded, project, t.id), 85, ev)

    def boom(self, target):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", boom)
    with pytest.raises(OSError):
        intel.create_skill(seeded, project.id, ev, "test")
    assert not [m for m in memory.search(seeded, project.id, "Skill make") if not m.deleted]
