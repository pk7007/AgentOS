"""The Boss loop through the CLI: objective -> plan -> schedule -> work -> independent review ->
acceptance -> gated delivery."""

import json

import pytest

from agentos.performance import WEIGHTS


@pytest.fixture
def ready(cli, home, repo, monkeypatch):
    cli(["init"])
    cli(["template", "seed"])
    cli(["project", "activate", str(repo)])
    monkeypatch.chdir(repo)
    return repo


def _j(result):
    code, out, err = result
    assert code == 0, err
    return json.loads(out)


def _plan_file(tmp_path, *tasks):
    p = tmp_path / "plan.json"
    p.write_text(json.dumps({"tasks": list(tasks)}), encoding="utf-8")
    return str(p)


def _start(cli, title="Ship CSV export", accept=("CSV export works",)):
    return _j(cli(["boss", "start", title, "--statement", "users export reports",
                   *[x for a in accept for x in ("--accept", a)], "--json"]))


def test_boss_loop_end_to_end(cli, ready, tmp_path):
    obj = _start(cli)
    assert obj["state"] == "open" and obj["acceptance"] == ["CSV export works"]
    plan = _plan_file(tmp_path,
                      {"key": "build", "title": "build export", "capabilities": ["implementation"]},
                      {"key": "doc", "title": "document export", "capabilities": ["implementation"],
                       "depends_on": ["build"]})
    created = _j(cli(["boss", "plan", obj["id"], "--file", plan, "--json"]))["created"]
    nxt = _j(cli(["boss", "next", obj["id"], "--json"]))
    dispatch = {d["task_id"]: d for d in nxt["dispatch"]}
    assert set(dispatch) == {created["build"]}  # doc waits on build
    assert dispatch[created["build"]]["status"] == "dispatch"
    assert nxt["executive_workers"] == []  # a routine objective gets no executive workers

    def work(task):
        _j(cli(["task", "start", task, "--json"]))
        iid = _j(cli(["agent", "admit", "--task", task, "--template", "implementer", "--host", "cc",
                      "--json"]))["instance_id"]
        review_task = _j(cli(["task", "add", f"review {task}", "--cap", "review", "--json"]))["id"]
        reviewer = _j(cli(["agent", "admit", "--task", review_task, "--template", "reviewer", "--host", "cc",
                           "--json"]))["instance_id"]
        proof = _j(cli(["evidence", "run", "--json", "--", "python", "-c", "print('ok')"]))
        scores = [x for k in WEIGHTS for x in ("--score", f"{k}=90")]
        ev = _j(cli(["eval", "record", iid, "--evaluator", reviewer, "--category", "coding", *scores,
                     "--evidence", proof["id"], "--json"]))
        _j(cli(["task", "done", task, "--json"]))
        return ev["id"], proof["id"]

    ev, proof = work(created["build"])
    assert cli(["boss", "deliver", obj["id"], "--criterion", f"0={proof}"])[0] == 3  # doc still open
    assert _j(cli(["boss", "accept", created["build"], "--eval", ev, "--json"]))["accepted"] is True
    assert cli(["boss", "accept", created["build"], "--eval", ev])[0] == 3  # already accepted
    ev2, _ = work(created["doc"])
    kinds = {b["kind"] for b in _j(cli(["boss", "bottlenecks", obj["id"], "--json"]))}
    assert "unaccepted_done" in kinds
    _j(cli(["boss", "accept", created["doc"], "--eval", ev2, "--json"]))
    review = _j(cli(["boss", "review", obj["id"], "--json"]))
    assert set(review["functions"]) == {"operations", "engineering", "hr", "finance", "intelligence",
                                        "security", "data", "risk", "quality"}
    code, _, err = cli(["boss", "deliver", obj["id"], "--json"])
    assert code == 3 and "criteria_without_evidence" in json.loads(err)["reasons"]
    done = _j(cli(["boss", "deliver", obj["id"], "--criterion", f"0={proof}", "--json"]))
    assert done["objective"]["state"] == "delivered"
    shown = _j(cli(["boss", "show", obj["id"], "--json"]))
    assert shown["report"]["criteria"][0]["evidence_id"] == proof
    assert [t["state"] for t in shown["tasks"]] == ["done", "done"]
    assert [o["state"] for o in _j(cli(["boss", "list", "--json"]))] == ["delivered"]
    assert cli(["audit", "verify"])[0] == 0


def test_boss_recover_retries_failed_task(cli, ready, tmp_path):
    obj = _start(cli)
    tid = _j(cli(["boss", "plan", obj["id"], "--file",
                  _plan_file(tmp_path, {"key": "a", "title": "a", "capabilities": ["implementation"]}),
                  "--json"]))["created"]["a"]
    assert cli(["boss", "recover", tid])[0] == 3  # not failed
    _j(cli(["task", "start", tid, "--json"]))
    _j(cli(["task", "fail", tid, "--json"]))
    assert _j(cli(["boss", "recover", tid, "--json"]))["action"] == "retry"


def test_boss_start_input_checks(cli, ready):
    assert cli(["boss", "start", "vague"])[0] == 3  # no acceptance criteria
    assert cli(["boss", "start", "x", "--accept", "a", "--tasks", "3"])[0] == 2  # some complexity flags only
    full = ["--tasks", "20", "--depth", "6", "--workstreams", "6", "--files", "50", "--difficulty", "5",
            "--uncertainty", "5", "--risk", "5", "--verify", "5"]
    assert _j(cli(["boss", "start", "big", "--accept", "a", *full, "--json"]))["complexity_band"] == "hierarchical"


def test_boss_plan_input_checks(cli, ready, tmp_path):
    obj = _start(cli)
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert cli(["boss", "plan", obj["id"], "--file", str(bad)])[0] == 2
    assert cli(["boss", "plan", obj["id"], "--file", str(tmp_path / "missing.json")])[0] == 2
    assert cli(["boss", "deliver", obj["id"], "--criterion", "nonsense"])[0] == 2
    assert cli(["boss", "show", "obj_000000000000"])[0] == 4


def test_boss_records_are_project_scoped(cli, ready, tmp_path, monkeypatch):
    obj = _start(cli)
    other = tmp_path / "other"
    other.mkdir()
    (other / ".git").mkdir()
    cli(["project", "activate", str(other)])
    monkeypatch.chdir(other)
    code, _, err = cli(["boss", "show", obj["id"], "--json"])
    assert code == 3 and "cross_project" in json.loads(err)["reasons"]
