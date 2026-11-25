import json


def test_task_flow_via_cli(cli, home, repo):
    cli(["init"])
    assert cli(["project", "activate", str(repo)])[0] == 0
    code, out, _ = cli(["task", "add", "Write parser", "--project", str(repo), "--cap", "python", "--json"])
    assert code == 0
    tid = json.loads(out)["id"]
    code, out, _ = cli(["task", "ready", "--project", str(repo), "--json"])
    assert [t["id"] for t in json.loads(out)] == [tid]
    assert cli(["task", "done", tid])[0] == 3
    assert cli(["task", "start", tid])[0] == 0
    assert cli(["task", "done", tid])[0] == 0


def test_task_add_in_unactivated_repo_denied(cli, home, repo):
    cli(["init"])
    code, _, _err = cli(["task", "add", "x", "--project", str(repo)])
    assert code == 4


def test_plan_score_cli(cli):
    code, out, _ = cli(["plan", "score", "--tasks", "1", "--workstreams", "1", "--json"])
    assert code == 0 and json.loads(out)["band"] == "single"
