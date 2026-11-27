"""Benchmarks of AgentOS's own hot paths, run against a throwaway database, never the live ledger.

Measured: admission plus release of a worker (the scheduling queue), one audit append, one memory search,
and audit chain verification. Admission is measured twice, on an empty ledger and again after the ledger
has grown, to show whether it slows as history accumulates (scaling efficiency). Results are stored in the
live ledger's `bench_runs` so `agentos bench history` can show the trend and flag a regression: the latest
median more than `REGRESSION_FACTOR` times the median of earlier runs."""

import sqlite3
import statistics
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from agentos import __version__, admission, audit, db, lifecycle, memory, projects, tasks, templates
from agentos.errors import UsageError
from agentos.lifecycle import AgentState
from agentos.memory import Layer
from agentos.util import new_id, now_iso

REGRESSION_FACTOR = 1.5
MIN_N, MAX_N = 5, 5000


def _definitions() -> Path:
    return Path(__file__).resolve().parents[2] / "definitions" / "agents"


@contextmanager
def _scratch():
    with tempfile.TemporaryDirectory(prefix="agentos-bench-") as tmp:
        root = Path(tmp)
        repo = root / "repo"
        repo.mkdir()
        conn = db.connect(root / "bench.db")
        try:
            db.migrate(conn)
            templates.seed(conn, _definitions(), actor="bench")
            yield conn, projects.activate(conn, repo, actor="bench")
        finally:
            conn.close()


def _stats(name: str, samples: list[float]) -> dict:
    ms = sorted(s * 1000 for s in samples)
    p95 = ms[min(len(ms) - 1, max(0, round(0.95 * len(ms)) - 1))]
    total = sum(samples)
    return {"name": name, "n": len(ms), "p50_ms": round(statistics.median(ms), 3), "p95_ms": round(p95, 3),
            "per_sec": round(len(ms) / total, 1) if total else 0.0}


def _admit_cycle(conn, project_id: str, n: int) -> list[float]:
    ids = [tasks.add_task(conn, project_id, f"bench {i}", actor="bench").id for i in range(n)]
    out = []
    for tid in ids:
        t0 = time.perf_counter()
        d = admission.admit(conn, admission.AdmitRequest(project_id=project_id, task_id=tid,
                                                          template_id="implementer", host="bench"), "bench")
        if not d.allowed:
            raise RuntimeError(f"benchmark admission was refused: {d.reasons}")
        lifecycle.transition(conn, d.instance_id, AgentState.CANCELLED, "bench", reason="bench")
        lifecycle.transition(conn, d.instance_id, AgentState.TERMINATED, "bench", reason="bench",
                             runtime_confirmed=True)
        out.append(time.perf_counter() - t0)
    return out


def run(n: int = 100) -> list[dict]:
    if not MIN_N <= n <= MAX_N:
        raise UsageError(f"n must be between {MIN_N} and {MAX_N}")
    results = []
    with _scratch() as (conn, prj):
        results.append(_stats("admit_release", _admit_cycle(conn, prj.id, n)))
        samples = []
        for i in range(n * 5):
            t0 = time.perf_counter()
            with db.write_tx(conn):
                audit.append_event(conn, "bench.event", "bench", {"i": i}, prj.id)
            samples.append(time.perf_counter() - t0)
        results.append(_stats("audit_append", samples))
        for i in range(n):
            memory.add(conn, prj.id, Layer.semantic, f"bench fact {i} about module {i % 7}", "bench", "bench")
        samples = []
        for i in range(n):
            t0 = time.perf_counter()
            memory.search(conn, prj.id, f"module {i % 7}")
            samples.append(time.perf_counter() - t0)
        results.append(_stats("memory_search", samples))
        t0 = time.perf_counter()
        checked = audit.verify_chain(conn).checked
        elapsed = time.perf_counter() - t0
        results.append({"name": "verify_chain", "n": checked, "p50_ms": round(elapsed * 1000, 3),
                        "p95_ms": round(elapsed * 1000, 3), "per_sec": round(checked / elapsed, 1) if elapsed else 0.0})
        late = _stats("admit_release_grown", _admit_cycle(conn, prj.id, n))
        late["slowdown_vs_empty"] = round(late["p50_ms"] / results[0]["p50_ms"], 2) if results[0]["p50_ms"] else None
        late["ledger_events"] = conn.execute("SELECT count(*) FROM events").fetchone()[0]
        results.append(late)
    return results


def record(conn: sqlite3.Connection, results: list[dict]) -> list[str]:
    ids, ts = [], now_iso()
    with db.write_tx(conn):
        for r in results:
            rid = new_id("bch")
            conn.execute("INSERT INTO bench_runs(id, name, n, p50_ms, p95_ms, per_sec, version, created_at)"
                         " VALUES (?,?,?,?,?,?,?,?)",
                         (rid, r["name"], r["n"], r["p50_ms"], r["p95_ms"], r["per_sec"], __version__, ts))
            ids.append(rid)
        audit.append_event(conn, "bench.recorded", "bench", {"runs": ids, "results": results})
    return ids


def history(conn: sqlite3.Connection, name: str | None = None, limit: int = 20) -> list[dict]:
    names = [name] if name else [r[0] for r in conn.execute("SELECT DISTINCT name FROM bench_runs ORDER BY name")]
    out = []
    for nm in names:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM bench_runs WHERE name=? ORDER BY created_at DESC, rowid DESC LIMIT ?", (nm, limit))]
        if not rows:
            continue
        latest, earlier = rows[0], rows[1:]
        base = statistics.median(r["p50_ms"] for r in earlier) if earlier else None
        out.append({"name": nm, "runs": len(rows), "latest_p50_ms": latest["p50_ms"], "baseline_p50_ms": base,
                    "regression": bool(base and latest["p50_ms"] > REGRESSION_FACTOR * base),
                    "trend": [r["p50_ms"] for r in reversed(rows)]})
    return out
