"""Generate plugin files for any host described by a small TOML profile (file names and folders only)."""

import json
from pathlib import Path

from agentos.errors import UsageError
from agentos.gen import GenResult, Writer, load_agents, load_plugin_meta, skill_text
from agentos.util import load_toml

PROFILE_KEYS = ("manifest_dir", "manifest_file", "instructions_file", "agents_dir", "skills_dir")


def load_profile(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        raise UsageError(f"host profile not found: {path}")
    prof = load_toml(path)
    missing = [k for k in PROFILE_KEYS if not isinstance(prof.get(k), str) or not prof[k]]
    if missing:
        raise UsageError("host profile is missing: " + ", ".join(missing))
    return prof


def _yaml_str(s: str) -> str:
    return json.dumps(s)  # a JSON string is a valid YAML double-quoted scalar


def _agent_md(t) -> str:
    tools = ["Read", "Grep", "Glob"] if t.read_only else ["Read", "Grep", "Glob", "Edit", "Write", "Bash"]
    if t.tools_allow:
        tools = list(t.tools_allow)
    tools = [x for x in tools if x not in t.tools_deny]
    lines = ["---", f"name: {t.id}", f"description: {_yaml_str(t.description)}", f"tools: {', '.join(tools)}"]
    if t.model_hint:
        lines.append(f"model: {t.model_hint}")
    lines += ["---", "", t.instructions.strip(), ""]
    return "\n".join(lines)


def _instructions(meta: dict, prof: dict) -> str:
    return "\n".join([
        f"# {meta['display_name']}",
        "",
        "This project is coordinated through the local `agentos` command.",
        f"Read `{prof['skills_dir']}/agentos/SKILL.md` before starting multi-agent work.",
        "",
        "- Ask `agentos agent admit` before starting any worker; if it is denied, do not start it.",
        "- Record evaluations with evidence. Never grade your own work.",
        "- Write a handover with `agentos handover create` before you stop mid-task.",
        "- Owner-only actions need the human owner at a real terminal.",
        "",
    ])


def generate(defs_dir: Path, profile_path: Path, out_dir: Path, force: bool = False) -> GenResult:
    prof = load_profile(profile_path)
    hooks_text = None
    if prof.get("hooks_file"):  # validated before anything is written
        from agentos.runtime import hooks_config

        hooks_text = json.dumps(hooks_config(prof.get("runtime_host", "")), indent=2) + "\n"
    meta = load_plugin_meta(defs_dir)
    agents = load_agents(defs_dir)
    w = Writer(out_dir, force)
    manifest = {"name": meta["name"], "version": meta["version"], "description": meta["description"]}
    if meta.get("author"):
        manifest["author"] = {"name": meta["author"]}
    w.write(f"{prof['manifest_dir']}/{prof['manifest_file']}", json.dumps(manifest, indent=2) + "\n")
    if prof.get("plugin_instructions", True):  # some hosts ignore it at a plugin root (use `host bootstrap`)
        w.write(prof["instructions_file"], _instructions(meta, prof))
    w.write(f"{prof['skills_dir']}/agentos/SKILL.md", skill_text(defs_dir))
    for t in agents:
        w.write(f"{prof['agents_dir']}/{t.id}.md", _agent_md(t))
    if hooks_text:
        w.write(prof["hooks_file"], hooks_text)
    return w.finish()
