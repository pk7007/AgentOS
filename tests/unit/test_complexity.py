from agentos.complexity import ComplexityInput, score


def _inp(**kw):
    base = dict(task_count=1, dependency_depth=0, workstreams=1, files_touched=1,
                domain_difficulty=1, uncertainty=0, risk=0, verification_effort=1)
    base.update(kw)
    return ComplexityInput(**base)


def test_trivial_task_is_single():
    r = score(_inp())
    assert r.band == "single" and r.suggested_agents == 1 and r.uncalibrated


def test_max_score_is_100():
    r = score(_inp(task_count=99, dependency_depth=99, workstreams=99, files_touched=999,
                   domain_difficulty=5, uncertainty=5, risk=5, verification_effort=5))
    assert r.score == 100 and r.band == "hierarchical" and r.suggested_agents == 4


def test_parallelism_caps_agents():
    r = score(_inp(task_count=99, dependency_depth=99, workstreams=1, files_touched=999,
                   domain_difficulty=5, uncertainty=5, risk=5, verification_effort=5))
    assert r.band == "hierarchical" and r.suggested_agents == 1


def test_mid_band():
    r = score(_inp(task_count=10, dependency_depth=3, workstreams=3, files_touched=25,
                   domain_difficulty=3, uncertainty=2, risk=2, verification_effort=3))
    assert 31 <= r.score <= 70 and r.suggested_agents <= 3
