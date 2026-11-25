"""`memory inspect` must not read another project's records (org-scoped records stay readable)."""

import json

from tests.conftest import make_repo


def _setup(cli, tmp_path):
    a, b = make_repo(tmp_path / "a"), make_repo(tmp_path / "b")
    cli(["init"])
    cli(["project", "activate", str(a)])
    cli(["project", "activate", str(b)])
    code, out, err = cli(["memory", "add", "project", "a secret plan", "--project", str(a), "--json"])
    assert code == 0, err
    return a, b, json.loads(out)["id"]


def test_inspect_other_project_denied(cli, home, tmp_path):
    _a, b, rid = _setup(cli, tmp_path)
    code, out, err = cli(["memory", "inspect", rid, "--project", str(b), "--json"])
    assert code == 3 and "cross_project" in err and "secret" not in out


def test_inspect_own_project_allowed(cli, home, tmp_path):
    a, _b, rid = _setup(cli, tmp_path)
    code, out, _ = cli(["memory", "inspect", rid, "--project", str(a), "--json"])
    assert code == 0 and json.loads(out)["content"] == "a secret plan"


def test_inspect_org_record_from_other_project(cli, home, tmp_path):
    a, b, _ = _setup(cli, tmp_path)
    code, out, err = cli(["memory", "add", "semantic", "shared fact", "--project", str(a), "--validated", "--org",
                          "--json"])
    assert code == 0, err
    rid = json.loads(out)["id"]
    assert cli(["memory", "inspect", rid, "--project", str(b)])[0] == 0
