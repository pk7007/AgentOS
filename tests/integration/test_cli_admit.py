import json


def _setup(cli, repo):
    cli(["init"])
    cli(["template", "seed"])
    cli(["project", "activate", str(repo)])
    _, out, _ = cli(["task", "add", "x", "--project", str(repo), "--json"])
    return json.loads(out)["id"]


def test_admit_allowed_then_duplicate_denied(cli, home, repo):
    tid = _setup(cli, repo)
    args = ["agent", "admit", "--project", str(repo), "--task", tid, "--template", "researcher", "--json"]
    code, out, _ = cli(args)
    assert code == 0 and json.loads(out)["allowed"] is True
    code, out, _ = cli(args)
    assert code == 3 and "duplicate" in json.loads(out)["reasons"]


def test_limits_show_and_raise_denied(cli, home):
    cli(["init"])
    code, out, _ = cli(["limits", "show", "--json"])
    assert code == 0 and json.loads(out)["max_concurrent"] == 4
    assert cli(["limits", "set", "max_concurrent", "2"])[0] == 0
    assert cli(["limits", "set", "max_concurrent", "9"])[0] == 3


def test_budget_set_and_show(cli, home):
    cli(["init"])
    assert cli(["budget", "set", "global", "tokens_est", "1000"])[0] == 0
    code, out, _ = cli(["budget", "show", "--json"])
    assert json.loads(out)[0]["limit"] == 1000
    assert cli(["budget", "set", "global", "usd", "5"])[0] == 3
