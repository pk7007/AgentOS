"""Native host adapters: install with backup, drift detection, rollback, uninstall, project bootstrap
and coexistence with other plugins. The second host is described by a profile with neutral names."""

import json
import shutil

import pytest

from agentos import adapters
from agentos.errors import NotFound, PolicyDenied, UsageError

PROFILE = ('manifest_dir = ".host-plugin"\nmanifest_file = "plugin.json"\ninstructions_file = "HOST.md"\n'
           'agents_dir = "agents"\nskills_dir = "skills"\nhooks_file = "hooks/hooks.json"\nruntime_host = "cc"\n'
           'register_hint = "host plugin add {dest}"\n')


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """No local profile from a developer checkout, and no real host CLI."""
    monkeypatch.setattr(adapters, "REPO", tmp_path / "no-repo")
    monkeypatch.setattr(adapters, "host_version", lambda a: "1.0.0")


@pytest.fixture
def cc_profile(tmp_path, home):
    path = home / "hosts" / "cc.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PROFILE, encoding="utf-8")
    return path


def test_codex_needs_no_profile_and_the_other_host_does(conn):
    a = adapters.resolve("codex")
    assert a.instructions_file == "AGENTS.md" and a.capabilities["hooks"] and "spawn_agent" in a.spawn_tools
    with pytest.raises(UsageError):
        adapters.resolve("cc")
    with pytest.raises(UsageError):
        adapters.resolve("nohost")


def test_a_profile_with_hooks_must_name_its_runtime(conn, tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text(PROFILE.replace('runtime_host = "cc"\n', ""), encoding="utf-8")
    with pytest.raises(UsageError):
        adapters.resolve("cc", bad)
    with pytest.raises(UsageError):
        adapters.resolve("cc", tmp_path / "missing.toml")


def test_install_writes_the_plugin_and_records_it(conn, cc_profile, home):
    r = adapters.install(conn, "cc", "test")
    dest = home / "plugins" / "cc"
    assert r["dest"] == str(dest.resolve()) and r["register"] == f"host plugin add {dest.resolve()}"
    assert (dest / ".host-plugin" / "plugin.json").exists() and (dest / "agents" / "lead.md").exists()
    hooks = json.loads((dest / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    assert set(hooks["hooks"]) == {"PreToolUse", "SubagentStart", "SubagentStop"}
    assert "agentos hook run cc" in json.dumps(hooks)
    assert adapters.installed(conn, "cc")["files"].keys() == adapters.tree(dest).keys()
    assert [h["status"] for h in adapters.history(conn, "cc")] == ["active"]


def test_install_refuses_a_folder_it_does_not_own(conn, tmp_path):
    dest = tmp_path / "busy"
    dest.mkdir()
    (dest / "mine.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(PolicyDenied) as e:
        adapters.install(conn, "codex", "test", dest)
    assert e.value.reasons == ["dest_not_empty"]
    assert (dest / "mine.txt").read_text(encoding="utf-8") == "keep"


def test_drift_finds_hand_edits_deletions_stale_definitions_and_host_updates(conn, tmp_path, monkeypatch):
    defs = tmp_path / "defs"
    shutil.copytree(adapters.DEFS, defs)
    dest = tmp_path / "codex"
    adapters.install(conn, "codex", "test", dest, defs=defs)
    assert adapters.drift(conn, "codex", defs=defs)["status"] == "in_sync"
    (dest / "agents" / "lead.toml").write_text("edited", encoding="utf-8")
    (dest / "config-snippet.toml").unlink()
    skill = defs / "skills" / "agentos" / "SKILL.md"
    skill.write_text(skill.read_text(encoding="utf-8") + "\nnew rule\n", encoding="utf-8")
    monkeypatch.setattr(adapters, "host_version", lambda a: "2.0.0")
    d = adapters.drift(conn, "codex", defs=defs)
    assert d["status"] == "drifted" and d["modified"] == ["agents/lead.toml"]
    assert d["missing"] == ["config-snippet.toml"] and "skills/agentos/SKILL.md" in d["stale"]
    assert d["host_changed"] and any("agentos host install codex" in x for x in d["actions"])
    with pytest.raises(UsageError):
        adapters.drift(conn, "cc")  # never configured
    adapters.uninstall(conn, "codex", "test")
    with pytest.raises(NotFound):
        adapters.drift(conn, "codex", defs=defs)


def test_update_backs_up_and_rollback_restores_exactly(conn, tmp_path):
    defs = tmp_path / "defs"
    shutil.copytree(adapters.DEFS, defs)
    dest = tmp_path / "codex"
    first = adapters.install(conn, "codex", "test", dest, defs=defs)
    (dest / "agents" / "lead.toml").write_text("my local tweak", encoding="utf-8")
    skill = defs / "skills" / "agentos" / "SKILL.md"
    skill.write_text(skill.read_text(encoding="utf-8") + "\nMARKER-ZX9\n", encoding="utf-8")
    second = adapters.install(conn, "codex", "test", dest, defs=defs)
    assert second["backed_up_modified"] == ["agents/lead.toml"]
    assert "MARKER-ZX9" in (dest / "skills" / "agentos" / "SKILL.md").read_text(encoding="utf-8")
    r = adapters.rollback(conn, "codex", "test")
    assert r["active"] == first["install_id"]
    assert (dest / "agents" / "lead.toml").read_text(encoding="utf-8") == "my local tweak"
    assert "MARKER-ZX9" not in (dest / "skills" / "agentos" / "SKILL.md").read_text(encoding="utf-8")
    assert [h["status"] for h in adapters.history(conn, "codex")] == ["active", "rolled_back"]
    with pytest.raises(PolicyDenied) as e:
        adapters.rollback(conn, "codex", "test")
    assert e.value.reasons == ["nothing_to_roll_back"]


def test_uninstall_keeps_files_you_edited(conn, tmp_path):
    dest = tmp_path / "codex"
    adapters.install(conn, "codex", "test", dest)
    (dest / "agents" / "lead.toml").write_text("mine", encoding="utf-8")
    r = adapters.uninstall(conn, "codex", "test")
    assert r["kept_modified"] == ["agents/lead.toml"] and r["removed"] > 5
    assert sorted(p.name for p in dest.rglob("*") if p.is_file()) == ["lead.toml"]
    assert adapters.installed(conn, "codex") is None
    with pytest.raises(NotFound):
        adapters.uninstall(conn, "codex", "test")
    with pytest.raises(NotFound):
        adapters.rollback(conn, "codex", "test")


def test_bootstrap_manages_only_its_own_block(conn, project, repo):
    notes = repo / "AGENTS.md"
    notes.write_text("# Team notes\n\nUse tabs.\n", encoding="utf-8")
    assert adapters.bootstrap(conn, repo, "codex", "test")["action"] == "added"
    text = notes.read_text(encoding="utf-8")
    assert text.startswith("# Team notes") and adapters.BEGIN in text and "--host codex" in text
    assert adapters.bootstrap(conn, repo, "codex", "test")["action"] == "unchanged"
    notes.write_text(text.replace("Follow the `agentos` skill.", "old"), encoding="utf-8")
    assert adapters.bootstrap(conn, repo, "codex", "test")["action"] == "updated"
    assert adapters.bootstrap(conn, repo, "codex", "test", remove=True)["action"] == "removed"
    assert notes.read_text(encoding="utf-8") == "# Team notes\n\nUse tabs.\n"
    assert adapters.bootstrap(conn, repo, "codex", "test", remove=True)["action"] == "absent"


def test_bootstrap_creates_and_removes_a_file_of_its_own(conn, project, repo, cc_profile):
    assert adapters.bootstrap(conn, repo, "cc", "test")["action"] == "added"
    assert (repo / "HOST.md").read_text(encoding="utf-8").startswith(adapters.BEGIN)
    adapters.bootstrap(conn, repo, "cc", "test", remove=True)
    assert not (repo / "HOST.md").exists()


def test_bootstrap_needs_an_active_project(conn, repo):
    with pytest.raises(PolicyDenied):
        adapters.bootstrap(conn, repo, "codex", "test")


def _plugin(root, name, hooks=None, agents=()):
    base = root / name
    for a in agents:
        (base / "agents").mkdir(parents=True, exist_ok=True)
        (base / "agents" / f"{a}.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    if hooks is not None:
        (base / "hooks").mkdir(parents=True, exist_ok=True)
        (base / "hooks" / "hooks.json").write_text(hooks if isinstance(hooks, str) else json.dumps(hooks),
                                                   encoding="utf-8")


def test_check_reports_shared_hooks_and_names_but_stays_compatible(conn, tmp_path, home):
    plugins = tmp_path / "plugins"
    gate = {"hooks": {"PreToolUse": [{"matcher": "Agent|Edit", "hooks": [{"type": "command", "command": "gate"}]},
                                     {"matcher": "Bash", "hooks": [{"type": "command", "command": "lint"}]}],
                      "SubagentStop": [{"hooks": [{"type": "command", "command": "log"}]}]}}
    _plugin(plugins, "other", gate, agents=["planner", "architect"])
    profile = home / "hosts" / "cc.toml"
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text(PROFILE + f'plugins_dir = "{plugins.as_posix()}"\n', encoding="utf-8")
    r = adapters.check("cc")
    assert r["verdict"] == "compatible"
    assert {(h["event"], h["matcher"]) for h in r["shared_hook_events"]} == {("PreToolUse", "Agent|Edit"),
                                                                            ("SubagentStop", None)}
    assert [a["name"] for a in r["same_name_agents"]] == ["planner"]
    _plugin(plugins, "broken", "{not json")
    assert adapters.check("cc")["verdict"] == "review"


def test_check_flags_a_second_agentos_install(conn, tmp_path):
    plugins = tmp_path / "plugins"
    dup = {"hooks": {"PreToolUse": [{"matcher": "spawn_agent",
                                     "hooks": [{"type": "command", "command": "agentos hook run codex"}]}]}}
    _plugin(plugins, "old-agentos", dup)
    profile = tmp_path / "codex.toml"
    profile.write_text(f'plugins_dir = "{plugins.as_posix()}"\n', encoding="utf-8")
    r = adapters.check("codex", profile)
    assert r["verdict"] == "conflict" and r["duplicate_agentos_hooks"]


def test_status_lists_every_host(conn, cc_profile):
    adapters.install(conn, "cc", "test")
    by_host = {s["host"]: s for s in adapters.status(conn)}
    assert by_host["codex"]["configured"] and by_host["codex"]["installed"] is None
    assert by_host["cc"]["installed"]["dest"].endswith("cc") and by_host["cc"]["host_version"] == "1.0.0"


def test_host_version_reads_the_cli_or_reports_none(monkeypatch):
    monkeypatch.undo()
    a = adapters.Adapter(id="x", profile={}, profile_path=None, executable="definitely-not-a-real-cli-xyz",
                         instructions_file="X.md", spawn_tools=[], plugins_dir=None, agents_home=None,
                         register_hint=None, capabilities={})
    assert adapters.host_version(a) is None
