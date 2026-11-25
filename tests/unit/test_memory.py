import pytest

from agentos import memory
from agentos.errors import PolicyDenied, UsageError
from agentos.memory import Layer


def _add(conn, project, text, **kw):
    return memory.add(conn, project.id, kw.pop("layer", Layer.semantic), text, source="test", author="t", **kw)


def test_add_and_search(conn, project):
    _add(conn, project, "Use WAL mode for the sqlite database")
    hits = memory.search(conn, project.id, "sqlite")
    assert len(hits) == 1 and hits[0].version == 1 and hits[0].validated is False


def test_layer_filter(conn, project):
    _add(conn, project, "deploy failed on friday", layer=Layer.failure)
    _add(conn, project, "deploy checklist", layer=Layer.procedural)
    assert [h.layer for h in memory.search(conn, project.id, "deploy", layers=[Layer.failure])] == [Layer.failure]


def test_validated_only(conn, project):
    _add(conn, project, "alpha fact", validated=True)
    _add(conn, project, "alpha guess")
    assert len(memory.search(conn, project.id, "alpha", validated_only=True)) == 1


def test_dedupe(conn, project):
    a = _add(conn, project, "same text")
    b = _add(conn, project, "same text")
    assert a.id == b.id


def test_secret_redacted_on_write(conn, project):
    r = _add(conn, project, "the api_key = sk-abcdefghijklmnopqrstuv is set")
    assert "sk-abc" not in memory.inspect(conn, r.id).content


@pytest.mark.parametrize("q", ['"foo', "AND", "*", "-x", "foo OR", "NEAR(", "'; DROP TABLE memory;--", "", "   "])
def test_fts_special_chars_safe(conn, project, q):
    _add(conn, project, "foo bar AND baz")
    memory.search(conn, project.id, q)


def test_special_chars_match_literally(conn, project):
    _add(conn, project, "status: AND gate passed")
    assert len(memory.search(conn, project.id, "AND gate")) == 1


def test_correct_supersedes(conn, project):
    r = _add(conn, project, "the port is 8080")
    v2 = memory.correct(conn, r.id, "the port is 9090", author="t")
    assert v2.version == 2 and v2.supersedes == r.id
    hits = memory.search(conn, project.id, "port")
    assert [h.id for h in hits] == [v2.id]


def test_delete_wipes_content(conn, project):
    r = _add(conn, project, "temporary note about cats")
    memory.delete(conn, r.id, actor="t")
    assert memory.search(conn, project.id, "cats") == []
    assert memory.inspect(conn, r.id).content == "" and memory.inspect(conn, r.id).deleted


def test_too_long_rejected(conn, project):
    with pytest.raises(UsageError):
        _add(conn, project, "x" * 20001)


def test_inactive_project_rejected(conn, project):
    from agentos import projects

    projects.deactivate(conn, project.id, actor="t")
    with pytest.raises(PolicyDenied):
        _add(conn, project, "nope")


def test_export(conn, project):
    _add(conn, project, "one")
    _add(conn, project, "two")
    assert len(memory.export(conn, project.id)) == 2
