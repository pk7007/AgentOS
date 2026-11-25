import json
import re
import tomllib
from pathlib import Path

from agentos.gen import codex, host, tomlw

ROOT = Path(__file__).resolve().parents[2]
DEFS = ROOT / "definitions"
VENDOR_WORDS = ["cla" + "ude", "anthro" + "pic"]


def test_tomlw_roundtrip():
    data = {
        "name": "x", "n": 3, "on": True, "ratio": 0.5, "tags": ["a", 'b"q'],
        "text": 'line one\nhas """ triple quotes\nand a \\ backslash\nends with quote"',
        "agents": {"max_threads": 4, "reviewer": {"description": "d", "config_file": "agents/reviewer.toml"},
                   "docs-helper": {"description": "tab\there"}},
    }
    assert tomllib.loads(tomlw.dumps(data)) == data


def test_codex_generate_files(tmp_path):
    result = codex.generate(DEFS, tmp_path)
    files = {p.relative_to(tmp_path).as_posix() for p in result.written}
    assert {".codex-plugin/plugin.json", "skills/agentos/SKILL.md", "agents/reviewer.toml",
            "config-snippet.toml", ".agents/plugins/marketplace.json"} <= files
    manifest = json.loads((tmp_path / ".codex-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "agentos" and manifest["skills"] == "./skills/"
    reviewer = tomllib.loads((tmp_path / "agents" / "reviewer.toml").read_text())
    assert reviewer["sandbox_mode"] == "read-only" and reviewer["model_reasoning_effort"] == "high"
    assert "model" not in reviewer
    market = json.loads((tmp_path / ".agents" / "plugins" / "marketplace.json").read_text())
    assert market["plugins"][0]["source"] == {"source": "local", "path": "./"}


def test_codex_snippet_limits(tmp_path):
    codex.generate(DEFS, tmp_path)
    snippet = tomllib.loads((tmp_path / "config-snippet.toml").read_text())
    assert snippet["agents"]["max_threads"] == 4 and snippet["agents"]["max_depth"] == 2
    assert snippet["agents"]["lead"]["config_file"] == "agents/lead.toml"


def test_generator_preserves_human_edits(tmp_path):
    codex.generate(DEFS, tmp_path)
    lead = tmp_path / "agents" / "lead.toml"
    lead.write_text("# my edit\n")
    again = codex.generate(DEFS, tmp_path)
    assert lead.read_text() == "# my edit\n" and lead in again.skipped_modified
    forced = codex.generate(DEFS, tmp_path, force=True)
    assert lead in forced.written and "my edit" not in lead.read_text()


def test_generator_does_not_clobber_unknown_existing_file(tmp_path):
    (tmp_path / "config-snippet.toml").write_text("mine = 1\n")
    result = codex.generate(DEFS, tmp_path)
    assert (tmp_path / "config-snippet.toml").read_text() == "mine = 1\n"
    assert tmp_path / "config-snippet.toml" in result.skipped_modified


def test_host_generate_uses_profile(tmp_path):
    profile = tmp_path / "hostx.toml"
    profile.write_text('manifest_dir = ".hostx"\nmanifest_file = "manifest.json"\n'
                       'instructions_file = "HOSTX.md"\nagents_dir = "agents"\nskills_dir = "skills"\n')
    out = tmp_path / "out"
    result = host.generate(DEFS, profile, out)
    assert (out / ".hostx" / "manifest.json").exists() and (out / "HOSTX.md").exists()
    assert (out / "skills" / "agentos" / "SKILL.md").exists()
    lead = (out / "agents" / "lead.md").read_text()
    assert lead.startswith("---\nname: lead\n") and "agentos agent admit" in lead
    assert len(result.written) == 1 + 1 + 1 + 6


def test_host_profile_missing_key(tmp_path):
    import pytest

    from agentos.errors import UsageError

    profile = tmp_path / "bad.toml"
    profile.write_text('manifest_dir = ".x"\n')
    with pytest.raises(UsageError):
        host.generate(DEFS, profile, tmp_path / "o")


def test_host_profile_with_bom_is_accepted(tmp_path):
    profile = tmp_path / "bom.toml"
    profile.write_bytes(b"\xef\xbb\xbf" + b'manifest_dir = ".h"\nmanifest_file = "m.json"\ninstructions_file = "H.md"\n'
                        b'agents_dir = "agents"\nskills_dir = "skills"\n')
    assert host.load_profile(profile)["manifest_dir"] == ".h"


def test_host_profile_malformed_is_usage_error(tmp_path):
    import pytest

    from agentos.errors import UsageError

    profile = tmp_path / "bad.toml"
    profile.write_text("this is = = not toml\n")
    with pytest.raises(UsageError):
        host.load_profile(profile)


def test_no_vendor_names_in_package():
    pattern = re.compile("|".join(VENDOR_WORDS), re.IGNORECASE)
    offenders = [str(p) for p in (ROOT / "src").rglob("*") if p.is_file() and p.suffix in {".py", ".sql", ".md", ".toml"}
                 and (pattern.search(p.read_text(encoding="utf-8")) or pattern.search(p.name))]
    assert offenders == []
