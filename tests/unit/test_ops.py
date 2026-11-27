"""Policy versions and per-project limits, retention, benchmarks, the MCP server, generated schemas and CLI
reference, and the Phase 9 intelligence and visibility additions."""

import json
import re
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agentos import (
    admission,
    audit,
    bench,
    db,
    governor,
    intel,
    lifecycle,
    mcp_server,
    memory,
    observe,
    performance,
    policy_log,
    projects,
    retention,
    tasks,
)
from agentos.errors import PolicyDenied, UsageError
from agentos.memory import Layer
from tests.conftest import add_evidence, add_instance

REPO = Path(__file__).resolve().parents[2]
ALL = list(performance.WEIGHTS)


# --- policy versions and per-project limits ---

def test_every_policy_change_raises_the_version_and_changes_the_hash(seeded, project, owner):
    before = policy_log.snapshot(seeded)
    governor.set_limit(seeded, "max_concurrent", 3, "t")
    governor.set_project_limit(seeded, project.id, "max_depth", 1, "t")
    after = policy_log.snapshot(seeded)
    assert after["version"] == before["version"] + 2 and after["hash"] != before["hash"]
    assert after["policy"]["project_limits"] == {project.id: {"max_depth": 1}}
    hist = policy_log.history(seeded)
    assert [h["kind"] for h in hist[-2:]] == ["limits.set", "limits.project"]
    assert hist[-1]["version"] == after["version"] and hist[-1]["change"]["to"] == 1
    assert policy_log.snapshot(seeded)["hash"] == after["hash"]  # reading changes nothing


def test_a_project_limit_only_tightens_and_loosening_it_needs_the_owner(seeded, project, task, owner):
    governor.set_project_limit(seeded, project.id, "max_concurrent", 1, "t")
    assert governor.get_limits(seeded, project.id).max_concurrent == 1
    assert governor.get_limits(seeded).max_concurrent == 4  # other projects are not affected
    governor.set_project_limit(seeded, project.id, "max_concurrent", 99, "t", owner=owner)
    assert governor.get_limits(seeded, project.id).max_concurrent == 4  # never above the global limit
    governor.set_project_limit(seeded, project.id, "max_concurrent", 1, "t")
    with pytest.raises(PolicyDenied) as exc:
        governor.set_project_limit(seeded, project.id, "max_concurrent", 2, "t")
    assert exc.value.reasons == ["owner_required"]
    with pytest.raises(PolicyDenied):
        governor.set_project_limit(seeded, project.id, "no_such_limit", 1, "t")
    with pytest.raises(UsageError):
        governor.set_project_limit(seeded, project.id, "max_depth", -1, "t")


def test_admission_enforces_the_project_slot_limit(seeded, project, task):
    governor.set_project_limit(seeded, project.id, "max_concurrent", 1, "t")
    req = admission.AdmitRequest(project_id=project.id, task_id=task.id, template_id="implementer", host="t")
    assert admission.admit(seeded, req, "t").allowed
    other = tasks.add_task(seeded, project.id, "second", actor="t")
    d = admission.admit(seeded, req.model_copy(update={"task_id": other.id}), "t")
    assert not d.allowed and d.reasons == ["project_max_concurrent"]


# --- retention ---

def _old(conn, table, column, row_id):
    conn.execute(f"UPDATE {table} SET {column}=? WHERE id=?",
                 ((datetime.now(UTC) - timedelta(days=200)).isoformat(), row_id))


def test_retention_removes_only_expired_data_and_needs_the_owner(seeded, project, task, owner):
    from agentos import comms

    a, b = add_instance(seeded, project, task), add_instance(seeded, project, task)
    read = comms.send(seeded, project.id, a, b, "old and read", "t")
    unread = comms.send(seeded, project.id, a, b, "old but unread", "t")
    seeded.execute("UPDATE messages SET read_at=created_at WHERE id=?", (read["id"],))
    _old(seeded, "messages", "created_at", read["id"])
    _old(seeded, "messages", "created_at", unread["id"])
    gone = memory.add(seeded, project.id, Layer.semantic, "a forgotten secret", "t", "t")
    memory.delete(seeded, gone.id, "t", project.id)
    _old(seeded, "memory", "created_at", gone.id)
    kept = memory.add(seeded, project.id, Layer.semantic, "still current", "t", "t")
    comms.claim(seeded, project.id, a, ["done.py"], "t")
    comms.release(seeded, project.id, a, "t")
    seeded.execute("UPDATE claims SET released_at='2000-01-01T00:00:00Z' WHERE path='done.py'")
    comms.claim(seeded, project.id, b, ["working.py"], "t")  # held: never removed
    events = seeded.execute("SELECT count(*) FROM events").fetchone()[0]
    # written 200 days ago but deleted today: it counts from its deletion, so it is kept for now
    assert retention.plan(seeded, 90)["would_remove"] == {"messages": 1, "bench_runs": 0, "memory": 0, "claims": 1}
    later = datetime.now(UTC) + timedelta(days=100)
    assert retention.plan(seeded, 90, now=later)["would_remove"]["memory"] == 1
    with pytest.raises(PolicyDenied):
        retention.apply(seeded, 90, "t")
    with pytest.raises(UsageError):
        retention.plan(seeded, 1)
    assert retention.apply(seeded, 90, "t", owner=owner, now=later)["removed"] == {
        "messages": 1, "bench_runs": 0, "memory": 1, "claims": 1}
    assert seeded.execute("SELECT count(*) FROM messages").fetchone()[0] == 1  # the unread one stays
    assert [c["path"] for c in comms.claims(seeded, project.id)] == ["working.py"]
    assert memory.search(seeded, project.id, "forgotten") == [] and memory.inspect(seeded, kept.id)
    assert seeded.execute("SELECT count(*) FROM events").fetchone()[0] == events + 1  # nothing pruned from audit
    assert audit.verify_chain(seeded).ok


# --- benchmarks ---

def test_bench_measures_without_touching_the_live_ledger_and_flags_a_regression(seeded):
    events = seeded.execute("SELECT count(*) FROM events").fetchone()[0]
    results = bench.run(10)
    assert {r["name"] for r in results} == {"admit_release", "audit_append", "memory_search", "verify_chain",
                                             "admit_release_grown"}
    assert all(r["p50_ms"] > 0 and r["per_sec"] > 0 for r in results)
    assert results[-1]["slowdown_vs_empty"] is not None
    assert seeded.execute("SELECT count(*) FROM events").fetchone()[0] == events
    bench.record(seeded, results)
    slow = [dict(r, p50_ms=r["p50_ms"] * 10) for r in results]
    bench.record(seeded, slow)
    h = {x["name"]: x for x in bench.history(seeded)}
    assert h["admit_release"]["regression"] is True and h["admit_release"]["runs"] == 2
    assert bench.history(seeded, "nothing") == []
    with pytest.raises(UsageError):
        bench.run(1)


# --- MCP server ---

def test_mcp_handles_the_protocol_and_refuses_what_it_does_not_offer(seeded, project, monkeypatch):
    monkeypatch.chdir(project.path)
    init = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                              "params": {"protocolVersion": "2025-03-26"}})
    assert init["result"]["protocolVersion"] == "2025-03-26" and "tools" in init["result"]["capabilities"]
    assert mcp_server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    names = {t["name"] for t in mcp_server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]}
    assert "agentos_dashboard" in names and not any("admit" in n for n in names)
    dash = mcp_server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                              "params": {"name": "agentos_dashboard", "arguments": {}}})["result"]
    assert dash["isError"] is False and json.loads(dash["content"][0]["text"])["project_id"] == project.id
    bad = mcp_server.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                             "params": {"name": "agentos_observe", "arguments": {"view": "secrets"}}})
    assert bad["result"]["isError"] is True
    assert mcp_server.handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                              "params": {"name": "agentos_admit", "arguments": {}}})["result"]["isError"]
    assert mcp_server.handle({"jsonrpc": "2.0", "id": 6, "method": "resources/list"})["error"]["code"] == -32601
    assert mcp_server.handle({"id": 7, "method": "ping"})["error"]["code"] == -32600


def test_mcp_serves_over_stdio_in_a_real_process(seeded, project, home):
    lines = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
             {"jsonrpc": "2.0", "method": "notifications/initialized"},
             {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "agentos_policy"}}]
    stdin = "\n".join(json.dumps(x) for x in lines) + "\nnot json\n"
    entry = "import sys; from agentos.cli import main; sys.exit(main(sys.argv[1:]))"
    r = subprocess.run([sys.executable, "-c", entry, "mcp", "serve"], input=stdin, capture_output=True,
                       text=True, timeout=60, check=False, cwd=project.path,
                       env={**__import__("os").environ, "AGENTOS_HOME": str(home), "PYTHONPATH": str(REPO / "src")})
    out = [json.loads(x) for x in r.stdout.splitlines()]
    assert r.returncode == 0 and [o.get("id") for o in out] == [1, 2, None]
    assert json.loads(out[1]["result"]["content"][0]["text"])["version"] >= 0
    assert out[2]["error"]["code"] == -32700


# --- generated files ---

def test_committed_schemas_match_the_models():
    from agentos.gen import schemas

    for name, text in schemas.expected().items():
        assert (REPO / "schemas" / name).read_text(encoding="utf-8") == text, f"run `agentos gen schemas` ({name})"
        assert json.loads(text)["$schema"].startswith("https://json-schema.org/")


def test_committed_reason_reference_matches_the_source():
    from agentos.gen import reasons

    committed = (REPO / "docs" / "REASONS.md").read_text(encoding="utf-8")
    assert committed == reasons.render(), "run: agentos gen docs"


def test_the_reason_scan_finds_every_kind_of_refusal():
    from agentos.gen import reasons

    found = reasons.scan()
    # one from each way a reason is written: a keyword list, reasons.append, and a Phase 9 module
    assert {"emergency_stop", "path_claimed", "owner_required", "cross_project", "tampered"} <= set(found)
    assert "admission.standing_reasons" in found["emergency_stop"]["where"]
    assert found["path_claimed"]["message"].startswith("another active worker holds")
    assert all(code == code.lower() and " " not in code for code in found)
    assert len(found) >= 100


def test_every_reason_has_a_remedy_and_a_meaning_and_none_is_stale():
    from agentos.gen import reason_guide, reasons

    found = reasons.scan()
    assert sorted(set(found) - set(reason_guide.REMEDY)) == [], "add a remedy in gen/reason_guide.py"
    assert sorted(set(reason_guide.REMEDY) - set(found)) == [], "remove the remedy of a reason that is gone"
    assert sorted(set(reason_guide.MEANING) - set(found)) == []
    no_meaning = [c for c, v in found.items() if not v["message"] and c not in reason_guide.MEANING]
    assert no_meaning == [], "add a meaning in gen/reason_guide.py"
    assert all(r.strip() for r in reason_guide.REMEDY.values())


def test_commands_named_in_remedies_parse():
    from agentos.cli import build_parser
    from agentos.gen import reason_guide

    parser = build_parser()
    for remedy in reason_guide.REMEDY.values():
        for cmd in re.findall(r"`agentos ([^`]+)`", remedy):
            parser.parse_args(cmd.split())


def test_a_message_built_from_parts_reads_in_order():
    from agentos.gen import reasons

    msg = reasons.scan()["path_claimed"]["message"]
    assert msg == "another active worker holds …", msg


def test_every_policy_refusal_names_a_reason():
    import ast

    missing = []
    for path in sorted((REPO / "src" / "agentos").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "PolicyDenied"
                    and not any(kw.arg == "reasons" for kw in node.keywords)):
                missing.append(f"{path.name}:{node.lineno}")
    assert missing == []


def test_committed_cli_reference_matches_the_parser():
    from agentos.gen import clidocs

    text = clidocs.render()
    assert (REPO / "docs" / "CLI.md").read_text(encoding="utf-8") == text, "run `agentos gen docs`"
    assert "### `agentos claim take`" in text and "`--after-minutes`" in text
    assert not re.search(r"[A-Za-z]:\\|/Users/|/home/", text), "the reference must not name a local folder"


# --- intelligence additions ---

def _grade(conn, worker, judge, value, project):
    return performance.record_eval(conn, worker, judge, "coding", {k: value for k in ALL},
                                   [add_evidence(conn, project.id)], actor="t")


def test_managers_are_judged_by_their_teams_graded_results(seeded, project, task):
    lead = add_instance(seeded, project, task, "lead")
    team = [add_instance(seeded, project, task, "implementer", parent=lead) for _ in range(3)]
    judge = add_instance(seeded, project, task, "reviewer")
    for w, v in zip(team, (90, 80, 40), strict=True):
        _grade(seeded, w, judge, v, project)
    r = intel.managers(seeded, project.id)
    assert r["leads"][0]["team"] == 3 and r["leads"][0]["pass_rate"] == 0.67 and r["leads"][0]["team_mean"] == 70.0
    assert r["templates"] == [{"template_id": "lead", "team_evaluations": 3, "team_mean": 70.0, "verdict": "effective"}]
    assert intel.managers(seeded, "prj_none")["leads"] == []


def test_calibration_flags_an_evaluator_far_from_the_others(seeded, project, task):
    fair1, fair2, harsh = (add_instance(seeded, project, task, "reviewer") for _ in range(3))
    for _ in range(2):
        w = add_instance(seeded, project, task, "implementer")
        _grade(seeded, w, fair1, 80, project)
        _grade(seeded, w, fair2, 82, project)
        _grade(seeded, w, harsh, 30, project)
    r = intel.calibration(seeded, project.id)
    assert r["flagged"] == [harsh] and r["instances_with_several_graders"] == 2
    assert {e["evaluator_id"]: e["status"] for e in r["evaluators"]}[fair1] == "calibrated"
    assert intel.calibration(seeded, project.id, min_shared=5)["flagged"] == []


def test_memory_quality_and_reuse_follow_what_is_validated_and_used(seeded, project):
    good = memory.add(seeded, project.id, Layer.semantic, "use the retry helper for network calls", "t", "t",
                      confidence=0.9, validated=True)
    weak = memory.add(seeded, project.id, Layer.semantic, "maybe something about caching", "t", "t", confidence=0.3)
    seeded.execute("UPDATE memory SET created_at=? WHERE id=?",
                   ((datetime.now(UTC) - timedelta(days=90)).isoformat(), weak.id))
    t = tasks.add_task(seeded, project.id, "network retry helper", actor="t")
    pack = intel.context_pack(seeded, t.id, record_for="t")
    assert good.id in {x["id"] for x in pack["included"]}
    q = intel.memory_quality(seeded, project.id)
    assert q["weakest"][0]["id"] == weak.id and weak.id in q["prune_candidates"] and good.id not in q["prune_candidates"]
    r = intel.reuse(seeded, project.id)
    assert r["validated_reused"] == 1 and r["reuse_rate"] == 1.0 and r["top"][0]["id"] == good.id
    assert intel.record_use(seeded, [], "t", project.id) == 0
    assert intel.record_use(seeded, ["mem_from_elsewhere"], "t", project.id) == 0


def test_route_falls_back_to_a_safe_available_tier(seeded, project):
    low = tasks.add_task(seeded, project.id, "small fix", risk="low", actor="t")
    high = tasks.add_task(seeded, project.id, "auth change", risk="high", actor="t")
    assert intel.route(seeded, low.id, available=["medium"])["selected"] == "medium"
    assert intel.route(seeded, low.id, available=["small"])["availability"] == "ok"
    r = intel.route(seeded, high.id, available=["small", "medium"])
    assert r["selected"] is None and r["fallback"] == [] and "escalate" in r["availability"]
    assert intel.route(seeded, low.id)["availability"].startswith("unknown")
    assert intel.host_tiers(None) is None


# --- visibility additions ---

def test_timeline_counts_each_day_and_spans_follow_each_worker(seeded, project, task):
    d = admission.admit(seeded, admission.AdmitRequest(project_id=project.id, task_id=task.id,
                                                       template_id="lead", host="t"), "t")
    lifecycle.transition(seeded, d.instance_id, "RUNNING", "t")
    lifecycle.transition(seeded, d.instance_id, "COMPLETED", "t")
    tl = observe.timeline(seeded, project.id, days=3)
    assert len(tl["days"]) == 3 and tl["series"]["admitted"][-1] == 1 and sum(tl["series"]["refused"]) == 0
    span = next(s for s in observe.spans(seeded, project.id) if s["span_id"] == d.instance_id)
    assert span["trace_id"] == d.instance_id and span["end"] and span["duration_s"] >= 0
    with pytest.raises(UsageError):
        observe.timeline(seeded, project.id, days=0)


def test_options_compare_alternatives_and_admit_uncertainty(seeded, project, task):
    t = tasks.add_task(seeded, project.id, "build", capabilities=["implementation"], actor="t")
    first = intel.options(seeded, t.id)
    assert first["verdict"] == "insufficient_evidence" and all("no_history" in o["risks"] for o in first["options"])
    judge = add_instance(seeded, project, task, "reviewer")
    for v in (90, 92, 88, 91):
        _grade(seeded, add_instance(seeded, project, task, "implementer"), judge, v, project)
    rated = {o["template_id"]: o for o in intel.options(seeded, t.id)["options"]}
    imp = rated["implementer"]
    assert imp["evaluations"] == 4 and imp["interval_90"][0] < imp["expected"] < imp["interval_90"][1]
    assert abs(imp["value_per_cost"] - imp["expected"] / imp["relative_cost"]) < 0.1


def _call(name, args):
    return mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                              "params": {"name": name, "arguments": args}})["result"]


def test_mcp_offers_only_protocol_versions_it_supports(seeded):
    for asked, got in (("1999-01-01", mcp_server.PROTOCOL), (None, mcp_server.PROTOCOL),
                       ("2024-11-05", "2024-11-05")):
        params = {"protocolVersion": asked} if asked else {}
        r = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": params})
        assert r["result"]["protocolVersion"] == got


def test_mcp_route_refuses_another_projects_task(seeded, project, tmp_path, monkeypatch):
    from tests.conftest import make_repo

    monkeypatch.chdir(project.path)
    other = projects.activate(seeded, make_repo(tmp_path / "other"), "t")
    theirs = tasks.add_task(seeded, other.id, "theirs", actor="t")
    mine = tasks.add_task(seeded, project.id, "mine", actor="t")
    refused = _call("agentos_route", {"task": theirs.id})
    assert refused["isError"] is True and "cross_project" in refused["content"][0]["text"]
    assert _call("agentos_route", {"task": theirs.id, "project": other.id})["isError"] is False
    assert _call("agentos_route", {"task": mine.id})["isError"] is False


def test_mcp_never_writes_the_ledger(seeded, project, monkeypatch):
    monkeypatch.chdir(project.path)
    before = seeded.execute("SELECT count(*) FROM events").fetchone()[0]
    conn = mcp_server._open_read_only()
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO settings(key, value) VALUES ('x', '1')")
    finally:
        conn.close()
    for view in mcp_server.VIEWS:
        assert _call("agentos_observe", {"view": view})["isError"] is False
    assert seeded.execute("SELECT count(*) FROM events").fetchone()[0] == before


def test_mcp_refuses_a_pending_migration_instead_of_applying_it(seeded, project, monkeypatch):
    monkeypatch.chdir(project.path)
    seeded.execute("DELETE FROM schema_migrations WHERE version=?", (db.SCHEMA_VERSION,))
    r = _call("agentos_status", {})
    assert r["isError"] is True and "agentos init" in r["content"][0]["text"]
    assert db.current_version(seeded) == db.SCHEMA_VERSION - 1


def test_options_recommend_only_with_enough_history_on_both_sides(seeded, project, task):
    t = tasks.add_task(seeded, project.id, "test it", capabilities=["testing"], actor="t")
    judge = add_instance(seeded, project, task, "lead")

    def grade(template, values):
        for v in values:
            _grade(seeded, add_instance(seeded, project, task, template), judge, v, project)

    grade("implementer", (95, 99))
    grade("reviewer", (55, 58))
    two_each = intel.options(seeded, t.id)
    assert two_each["verdict"] == "insufficient_evidence"  # separated, but two grades are not enough
    imp = next(o for o in two_each["options"] if o["template_id"] == "implementer")
    assert imp["interval_90"][0] < imp["expected"] - 2 * intel.MIN_HALF_WIDTH  # t with 1 df is wide
    grade("implementer", (95,))
    grade("reviewer", (55,))
    assert intel.options(seeded, t.id)["verdict"] == "recommend"


def test_identical_grades_still_get_an_interval():
    assert intel.t90(1) > intel.t90(10) > intel.t90(500) == intel.Z90
    with pytest.raises(ValueError):
        intel.t90(0)


def test_the_breaker_is_a_policy_change_and_milder_needs_the_owner(seeded, owner):
    from agentos import health

    before = policy_log.snapshot(seeded)
    assert before["policy"]["breaker"] == {"window": 3, "floor": 30.0}
    assert health.set_breaker(seeded, "t", window=2, floor=40)["new"] == {"window": 2, "floor": 40.0}  # stricter
    with pytest.raises(PolicyDenied) as exc:
        health.set_breaker(seeded, "t", floor=10)
    assert exc.value.reasons == ["owner_required"]
    health.set_breaker(seeded, "t", window=5, owner=owner)
    after = policy_log.snapshot(seeded)
    assert after["version"] == before["version"] + 2 and after["hash"] != before["hash"]
    assert [h["kind"] for h in policy_log.history(seeded)][-2:] == ["health.breaker_set", "health.breaker_set"]
    for bad in ({"window": 0}, {"window": 21}, {"floor": 101}):
        with pytest.raises(UsageError):
            health.set_breaker(seeded, "t", **bad)


def test_host_tiers_come_from_the_host_profile_models_table(seeded, project, home):
    t = tasks.add_task(seeded, project.id, "risky", risk="high", actor="t")
    assert intel.host_tiers("codex") is None  # no profile: unknown, never guessed
    assert intel.route(seeded, t.id, available=intel.host_tiers("codex"))["availability"].startswith("unknown")
    (home / "hosts").mkdir(parents=True, exist_ok=True)
    (home / "hosts" / "codex.toml").write_text('[models]\nsmall = "s-model"\nmedium = "m-model"\nlarge = ""\n',
                                              encoding="utf-8")
    assert intel.host_tiers("codex") == ["small", "medium"]
    r = intel.route(seeded, t.id, available=intel.host_tiers("codex"))
    assert r["tier"] == "large" and r["selected"] is None and "escalate" in r["availability"]  # never smaller
