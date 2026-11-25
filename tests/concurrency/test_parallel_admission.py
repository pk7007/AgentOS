import multiprocessing as mp
import os


def _worker(home, project_id, task_id, out):
    os.environ["AGENTOS_HOME"] = home
    from agentos import admission, db

    conn = db.connect()
    try:
        d = admission.admit(conn, admission.AdmitRequest(project_id=project_id, task_id=task_id,
                                                         template_id="researcher", host="race"), actor="race")
        out.put((d.allowed, d.reasons))
    finally:
        conn.close()


def test_parallel_processes_never_exceed_limit(seeded, project, home):
    from agentos import lifecycle, tasks

    ids = [tasks.add_task(seeded, project.id, f"t{i}", actor="t").id for i in range(12)]
    ctx = mp.get_context("spawn")
    out = ctx.Queue()
    procs = [ctx.Process(target=_worker, args=(str(home), project.id, tid, out)) for tid in ids]
    for p in procs:
        p.start()
    for p in procs:
        p.join(120)
    results = [out.get(timeout=10) for _ in procs]
    allowed = [r for r in results if r[0]]
    denied = [r for r in results if not r[0]]
    assert len(allowed) == 4 and len(denied) == 8
    assert all("max_concurrent" in reasons for _, reasons in denied)
    assert lifecycle.active_count(seeded) == 4
