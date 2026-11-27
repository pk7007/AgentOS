"""Read-only views: each must show exactly what the ledger and audit log hold."""

from agentos import admission, audit, boss, governance, governor, observe, performance, tasks, workforce
from agentos.util import new_id, now_iso
from tests.conftest import add_evidence

ALL = list(performance.WEIGHTS)


def _worker(conn, project, task_id, template="implementer", state="RUNNING", parent=None):
    iid, ts = new_id("ag"), now_iso()
    conn.execute(
        "INSERT INTO agent_instances(id, template_id, template_version, project_id, task_id, parent_id, depth,"
        " host, state, created_at, updated_at) VALUES (?, ?, 1, ?, ?, ?, ?, 'test', ?, ?, ?)",
        (iid, template, project.id, task_id, parent, 1 if parent else 0, state, ts, ts))
    return iid


def test_active_agents_lists_slot_holders_with_what_the_host_reported(seeded, project, task):
    run = _worker(seeded, project, task.id)
    _worker(seeded, project, task.id, state="COMPLETED")
    gone = _worker(seeded, project, task.id, state="TERMINATED")
    seeded.execute("INSERT INTO runtime_bindings(instance_id, host, native_agent_id, claimed_at, started_at) "
                   "VALUES (?, 'test', 'native-7', ?, ?)", (run, now_iso(), now_iso()))
    rows = {a["id"]: a for a in observe.active_agents(seeded, project.id)}
    assert set(rows) == {run, gone}
    assert rows[run]["runtime"]["native_agent_id"] == "native-7" and rows[run]["task"] == "fixture task"
    assert rows[gone]["state"] == "TERMINATED (unconfirmed)" and rows[gone]["runtime"] is None
    assert observe.active_agents(seeded, "prj_other") == []


def test_hierarchy_nests_children_under_parents(seeded, project, task):
    lead = _worker(seeded, project, task.id, "lead")
    a = _worker(seeded, project, task.id, parent=lead)
    _worker(seeded, project, task.id, "reviewer", parent=a)
    _worker(seeded, project, task.id, state="ARCHIVED")
    roots = observe.hierarchy(seeded, project.id)
    assert [r["id"] for r in roots] == [lead]
    assert roots[0]["children"][0]["id"] == a and roots[0]["children"][0]["children"][0]["template_id"] == "reviewer"
    assert len(observe.hierarchy(seeded, project.id, include_finished=True)) == 2
    text = observe.render_tree(roots)
    assert text.splitlines()[0].startswith("`-- lead") and "    `-- implementer" in text
    assert observe.render_tree([]) == "(no workers)"


def test_progress_per_objective(seeded, project):
    obj = boss.create_objective(seeded, project.id, "ship", acceptance=["tests pass"], actor="t")
    ids = [tasks.add_task(seeded, project.id, f"t{i}", actor="t").id for i in range(3)]
    seeded.execute(f"UPDATE tasks SET objective_id=? WHERE id IN ({','.join('?' * 3)})", (obj.id, *ids))
    tasks.set_state(seeded, ids[0], "running", "t")
    tasks.set_state(seeded, ids[0], "done", "t")
    tasks.set_state(seeded, ids[1], "cancelled", "t")
    loose = tasks.add_task(seeded, project.id, "loose", actor="t")
    tasks.set_state(seeded, loose.id, "blocked", "t")
    p = observe.progress(seeded, project.id)
    first, rest = p["objectives"]
    assert first["title"] == "ship" and first["percent_done"] == 50 and first["tasks"] == {"done": 1,
                                                                                        "cancelled": 1,
                                                                                        "pending": 1}
    assert rest["objective_id"] is None and rest["percent_done"] == 0
    assert p["blocked"] == [{"id": loose.id, "title": "loose"}]


def test_recruitment_and_termination_history(seeded, project, task):
    ok = admission.admit(seeded, admission.AdmitRequest(project_id=project.id, task_id=task.id,
                                                        template_id="implementer", host="test"), "t")
    governance.emergency_stop(seeded, "t", "drill")
    admission.admit(seeded, admission.AdmitRequest(project_id=project.id, task_id=task.id,
                                                   template_id="implementer", host="test"), "t")
    r = observe.recruitment(seeded, project.id)
    assert r["counts"] == {"agent.admitted": 1, "agent.admission_denied": 1}
    assert r["events"][0]["kind"] == "agent.admission_denied" and r["events"][1]["instance_id"] == ok.instance_id
    workforce.terminate(seeded, ok.instance_id, "drill", "t")
    t = observe.terminations(seeded, project.id)
    assert t["events"][0]["kind"] == "workforce.terminated"
    assert [(u["id"], u["state"]) for u in t["unconfirmed_stops"]] == [(ok.instance_id, "CANCELLED")]
    assert observe.active_agents(seeded, project.id)[0]["state"] == "CANCELLED (stop pending)"


def test_performance_resources_and_controls(seeded, project, task, owner):
    w = _worker(seeded, project, task.id)
    performance.record_eval(seeded, w, _worker(seeded, project, task.id, "reviewer"), "coding",
                            {k: 80 for k in ALL}, [add_evidence(seeded, project.id)], actor="t")
    assert {"template_id": "implementer", "evaluations": 1, "mean": 80.0}.items() <=         observe.performance_records(seeded)[0].items()
    governor.record_usage(seeded, w, "tokens_est", 1234, "t")
    governor.set_budget(seeded, "project", project.id, "tokens_est", 5000, "t", owner)
    r = observe.resources(seeded, project.id)
    assert r["used"]["project"]["tokens_est"] == 1234 and r["slots_held"] == 2 and r["paid_spend_cap_usd"] == 0
    assert r["budgets"][0]["remaining"] == 5000 - 1234
    c = observe.controls(seeded)
    assert c["emergency_stop"] is False and c["owner_pin_set"] is False
    governance.emergency_stop(seeded, "t", "drill")
    assert observe.controls(seeded)["emergency_stop"] is True


def test_experiments_and_accepted_and_rejected_changes(seeded, project):
    ts = now_iso()
    for eid, status in (("exp_a", "promoted"), ("exp_b", "abandoned"), ("exp_c", "trialing")):
        seeded.execute("INSERT INTO experiments(id, project_id, kind, target, suite, hypothesis, champion,"
                       " challenger, status, created_at, decided_at, actor) VALUES (?, ?, 'template', 'implementer',"
                       " 's', 'h', '{}', '{}', ?, ?, ?, 't')", (eid, project.id, status, ts, ts))
    seeded.execute("INSERT INTO rehabilitations VALUES ('rh_1', 'implementer', 1, 2, 60, 'failed', ?, ?)", (ts, ts))
    denied = governance.request_approval(seeded, "template.retire", {"id": "x"}, "t")
    governance.deny(seeded, denied.id, "t")
    assert observe.experiments(seeded, project.id)["counts"] == {"promoted": 1, "abandoned": 1, "trialing": 1}
    ch = observe.changes(seeded, project.id)
    assert [c["id"] for c in ch["accepted"]] == ["exp_a"]
    assert {c["id"] for c in ch["rejected"]} == {"exp_b", "rh_1", denied.id}


def test_incidents_are_sorted_by_severity_and_include_a_broken_chain(seeded, project, task):
    from agentos.db import write_tx

    with write_tx(seeded):
        audit.append_event(seeded, "runtime.spawn_denied", "hook", {"tool": "Agent", "reasons": ["no_admission"]},
                           project.id)
    w = _worker(seeded, project, task.id)
    performance.record_eval(seeded, w, _worker(seeded, project, task.id, "reviewer"), "coding",
                            {k: 80 for k in ALL}, [add_evidence(seeded, project.id)],
                            flags=["security_violation"], actor="t")
    inc = observe.incidents(seeded, project.id)
    kinds = [i["kind"] for i in inc["incidents"]]
    assert set(kinds) == {"runtime.spawn_denied", "eval.flagged", "template.quarantined"}
    assert kinds[-1] == "runtime.spawn_denied" and inc["counts"] == {"high": 2, "medium": 1} and inc["audit_chain_ok"]
    seeded.execute("UPDATE events SET payload='{}' WHERE seq=1")
    broken = observe.incidents(seeded, project.id)
    assert not broken["audit_chain_ok"] and "audit.chain_broken" in [i["kind"] for i in broken["incidents"]]


def test_dashboard_summarises_and_renders(seeded, project, task):
    _worker(seeded, project, task.id)
    governance.emergency_stop(seeded, "t", "drill")
    d = observe.dashboard(seeded, project.id)
    assert d["active_agents"] == 1 and d["slots"] == "1/4" and d["controls"]["emergency_stop"]
    text = observe.render_dashboard(d)
    assert "emergency stop: ON" in text and "audit chain: ok" in text and "(no objective)" in text
