"""The self-improvement loop through the CLI: cases, a template experiment run blind to promotion,
and the owner gate on replacing a working template by hand."""

import json

import pytest

from agentos.performance import WEIGHTS

CHECK = ["--", "python", "-c", "pass"]


@pytest.fixture
def ready(cli, home, repo, monkeypatch):
    cli(["init"])
    cli(["template", "seed"])
    cli(["project", "activate", str(repo)])
    monkeypatch.chdir(repo)
    return repo


def _j(result):
    code, out, err = result
    assert code == 0, err
    return json.loads(out)


def _reviewer(cli, n):
    task = _j(cli(["task", "add", f"review {n}", "--cap", "review", "--json"]))["id"]
    return _j(cli(["agent", "admit", "--task", task, "--template", "reviewer", "--host", "cc",
                   "--json"]))["instance_id"]


def _trial(cli, exp, case, arm, value, reviewer):
    t = _j(cli(["improve", "trial", exp, case, "--arm", arm, "--host", "cc", "--json"]))
    for state in ("RUNNING", "COMPLETED"):
        _j(cli(["agent", "transition", t["instance_id"], state, "--json"]))
    proof = _j(cli(["improve", "check", t["trial_id"], "--json"]))
    scores = [x for k in WEIGHTS for x in ("--score", f"{k}={value}")]
    ev = _j(cli(["eval", "record", t["instance_id"], "--evaluator", reviewer, "--category", "coding", *scores,
                 "--evidence", proof["id"], "--json"]))
    _j(cli(["improve", "score", t["trial_id"], ev["id"], "--json"]))


def _spec(tmp_path):
    spec = tmp_path / "impl.toml"
    spec.write_text('id = "implementer"\nname = "x"\nrole = "implementer"\ndepartment = "engineering"\n'
                    'description = "x"\ncapabilities = ["python"]\ninstructions = "x"\n', encoding="utf-8")
    return str(spec)


def test_a_template_experiment_runs_to_promotion(cli, ready, tmp_path):
    cases = []
    for i, split in enumerate(["representative"] * 3 + ["heldout"] * 2):
        cases.append(_j(cli(["improve", "case", "--suite", "core", "--title", f"case {i} reads the settings file",
                             "--split", split, "--cap", "python", "--json", *CHECK]))["id"])
    listed = _j(cli(["improve", "cases", "--suite", "core", "--json"]))
    assert sum("title" in c for c in listed) == 3  # held-out cases stay hidden

    base = _j(cli(["template", "inspect", "implementer", "--json"]))["instructions"]
    changes = tmp_path / "changes.toml"
    changes.write_text(f"instructions = '''{base}\nRun the check command before you report.'''\n", encoding="utf-8")
    bad = tmp_path / "bad.toml"
    bad.write_text('security_class = "elevated"\n', encoding="utf-8")
    code, _, err = cli(["improve", "propose", "--suite", "core", "--template", "implementer", "--file", str(bad),
                        "--hypothesis", "x", "--json"])
    assert code == 3 and json.loads(err)["reasons"] == ["not_tunable"]
    exp = _j(cli(["improve", "propose", "--suite", "core", "--template", "implementer", "--file", str(changes),
                  "--hypothesis", "checking first raises reliability", "--json"]))
    assert exp["status"] == "trialing"

    reviewers = [_reviewer(cli, 1), _reviewer(cli, 2)]
    for i, case in enumerate(cases):
        _trial(cli, exp["id"], case, "champion", 70, reviewers[i % 2])
        _trial(cli, exp["id"], case, "challenger", 82, reviewers[i % 2])
    shown = _j(cli(["improve", "show", exp["id"], "--json"]))
    assert len(shown["trials"]) == 10 and all("arm" not in t for t in shown["trials"])

    code, _, err = cli(["improve", "decide", exp["id"], "--json"])
    assert code == 3 and json.loads(err)["reasons"] == ["gate_not_passed"]
    _j(cli(["improve", "gate", exp["id"], "--json", *CHECK]))
    assert _j(cli(["improve", "status", exp["id"], "--json"]))["representative"]["delta"] == pytest.approx(12)
    assert _j(cli(["improve", "decide", exp["id"], "--json"]))["status"] == "promoted"
    champ = _j(cli(["template", "inspect", "implementer", "--json"]))
    assert champ["version"] == 2 and "Run the check command before you report." in champ["instructions"]

    assert [e["status"] for e in _j(cli(["improve", "experiments", "--json"]))] == ["promoted"]
    assert _j(cli(["improve", "monitor", "--json"]))[0]["status"] == "monitoring"
    assert {p["name"] for p in _j(cli(["improve", "policies", "--json"]))} >= {"recruit.w_match"}
    retro = _j(cli(["improve", "retro", "--json"]))
    assert _j(cli(["improve", "retro", "--show", retro["id"], "--json"]))["scope"] == "project"


def test_policy_experiment_needs_a_value_and_cases(cli, ready):
    assert cli(["improve", "propose", "--suite", "core", "--policy", "recruit.w_match"])[0] == 2
    code, _, err = cli(["improve", "propose", "--suite", "core", "--policy", "recruit.w_match", "--value", "0.6",
                        "--hypothesis", "x", "--json"])
    assert code == 3 and json.loads(err)["reasons"] == ["not_enough_cases"]


def test_replacing_a_working_template_needs_the_owner(cli, ready, tmp_path):
    code, _, err = cli(["template", "add", _spec(tmp_path), "--json"])
    assert code == 3 and "owner" in err
    assert _j(cli(["template", "inspect", "implementer", "--json"]))["version"] == 1


def test_the_owner_can_replace_a_working_template(cli, ready, tmp_path, owner_tty):
    assert _j(cli(["template", "add", _spec(tmp_path), "--json"]))["version"] == 2
