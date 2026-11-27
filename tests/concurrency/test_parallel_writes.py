"""Parallel processes writing at once: a budget is never overspent, identical memory is stored once, and
the audit chain stays valid."""

import multiprocessing as mp
import os

from agentos import audit, governor, memory


def _charge(home, instance_id, out):
    os.environ["AGENTOS_HOME"] = home
    from agentos import db, governor
    from agentos.errors import PolicyDenied

    conn = db.connect()
    try:
        governor.record_usage(conn, instance_id, "tokens_est", 300, "race")
        out.put("charged")
    except PolicyDenied:
        out.put("denied")
    finally:
        conn.close()


def _remember(home, project_id, out):
    os.environ["AGENTOS_HOME"] = home
    from agentos import db, memory
    from agentos.memory import Layer

    conn = db.connect()
    try:
        out.put(memory.add(conn, project_id, Layer.semantic, "one shared fact", "race", "race").id)
    finally:
        conn.close()


def _run(target, args_list):
    ctx = mp.get_context("spawn")
    out = ctx.Queue()
    procs = [ctx.Process(target=target, args=(*a, out)) for a in args_list]
    for p in procs:
        p.start()
    for p in procs:
        p.join(120)
    return [out.get(timeout=10) for _ in procs]


def test_parallel_usage_never_overspends_a_budget(seeded, project, instance, home, owner):
    governor.set_budget(seeded, "project", project.id, "tokens_est", 1000, "t", owner)
    results = _run(_charge, [(str(home), instance)] * 8)
    assert results.count("charged") == 3 and results.count("denied") == 5
    assert governor._used(seeded, "project", project.id, "tokens_est") == 900
    assert audit.verify_chain(seeded).ok


def test_parallel_identical_memory_is_stored_once(seeded, project, home):
    ids = _run(_remember, [(str(home), project.id)] * 6)
    assert len(set(ids)) == 1
    assert seeded.execute("SELECT count(*) FROM memory WHERE content='one shared fact'").fetchone()[0] == 1
    assert memory.inspect(seeded, ids[0]).content == "one shared fact"
    assert audit.verify_chain(seeded).ok
