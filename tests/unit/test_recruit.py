from agentos import performance, recruit, templates
from agentos.performance import WEIGHTS
from agentos.templates import AgentTemplate, TemplateStatus
from agentos.util import new_id, now_iso


def _tpl(conn, tid, caps):
    templates.add_template(conn, AgentTemplate(id=tid, name=tid, role="r", department="d", description="d",
                                               capabilities=caps, instructions="i"), actor="t")


def _inst(conn, tid, project, task):
    iid, ts = new_id("ag"), now_iso()
    conn.execute(
        "INSERT INTO agent_instances(id, template_id, template_version, project_id, task_id, parent_id, depth,"
        " host, state, created_at, updated_at) VALUES (?, ?, 1, ?, ?, NULL, 0, 'test', 'RUNNING', ?, ?)",
        (iid, tid, project.id, task.id, ts, ts))
    return iid


def _evals(conn, iid, score, n):
    for i in range(n):
        performance.record_eval(conn, iid, f"rev{i}", "coding", {k: score for k in WEIGHTS},
                                evidence=["pytest"], actor="t")


def test_rank_prefers_match(seeded):
    ranked = recruit.rank(seeded, ["python", "testing"])
    assert ranked[0].template_id == "implementer" and ranked[0].match == 1.0
    assert all(c.match > 0 for c in ranked)


def test_rank_prefers_history_on_equal_match(conn, project, task):
    _tpl(conn, "alpha", ["x"])
    _tpl(conn, "beta", ["x"])
    _evals(conn, _inst(conn, "beta", project, task), 95, 5)
    assert [c.template_id for c in recruit.rank(conn, ["x"])] == ["beta", "alpha"]


def test_inactive_excluded(seeded):
    templates.set_status(seeded, "implementer", TemplateStatus.suspended, actor="t", reason="x")
    assert "implementer" not in [c.template_id for c in recruit.rank(seeded, ["python"])]


def test_high_risk_requires_proven(conn, project, task):
    _tpl(conn, "fresh", ["sec"])
    _tpl(conn, "proven", ["sec"])
    _evals(conn, _inst(conn, "proven", project, task), 90, 3)
    assert [c.template_id for c in recruit.rank(conn, ["sec"], high_risk=True)] == ["proven"]


def test_gap_reported(seeded):
    assert recruit.rank(seeded, ["cobol"]) == []
    assert recruit.missing_capabilities(seeded, ["cobol", "python"]) == ["cobol"]
