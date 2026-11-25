import json


def test_handover_create_and_resume_via_cli(cli, home, repo):
    cli(["init"])
    cli(["project", "activate", str(repo)])
    code, out, err = cli(["handover", "create", "--project", str(repo), "--objective", "o", "--next", "n",
                          "--host", "codex", "--json"])
    assert code == 0, err
    hid = json.loads(out)["id"]
    code, out, _ = cli(["handover", "resume", hid, "--project", str(repo), "--host", "cc", "--json"])
    assert code == 0 and json.loads(out)["ok"] is True
    assert cli(["handover", "resume", hid, "--project", str(repo)])[0] == 3
