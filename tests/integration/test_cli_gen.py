import json


def test_gen_codex_cli(cli, tmp_path):
    out = tmp_path / "codex"
    code, stdout, err = cli(["gen", "codex", "--out", str(out), "--json"])
    assert code == 0, err
    data = json.loads(stdout)
    assert data["skipped_modified"] == [] and len(data["written"]) >= 10
    assert (out / ".codex-plugin" / "plugin.json").exists()


def test_gen_host_cli_requires_profile(cli, tmp_path):
    code, _, err = cli(["gen", "host", "--profile", str(tmp_path / "nope.toml"), "--out", str(tmp_path / "o")])
    assert code == 2 and "profile" in err


def test_gen_needs_no_init(cli, home, tmp_path):
    # `home` is a fresh AGENTOS_HOME with no `init`; generation must not need state.
    assert cli(["gen", "codex", "--out", str(tmp_path / "c")])[0] == 0
    assert not list(home.rglob("*.db"))
