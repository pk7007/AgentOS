"""Every `agentos ...` command shown in the skill must parse with the real CLI, and its score keys must exist.

Hosts copy these lines verbatim, so a drifted example breaks every session that follows the skill.
"""

import re
import shlex
from pathlib import Path

import pytest

from agentos.cli import build_parser
from agentos.performance import WEIGHTS

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "definitions" / "skills" / "agentos" / "SKILL.md"
README = ROOT / "README.md"
GUIDES = [ROOT / "docs" / n for n in ("RUNBOOK.md", "TROUBLESHOOTING.md", "EXAMPLES.md")]


def _commands(doc: Path = SKILL) -> list[str]:
    text = doc.read_text(encoding="utf-8")
    spans = re.findall(r"`(agentos [^`]+)`", text)
    blocks = re.findall(r"```[a-z]*\n(.*?)```", text, re.DOTALL)
    lines = [ln.split("#")[0].strip() for b in blocks for ln in b.splitlines() if ln.strip().startswith("agentos ")]
    return spans + lines


def _concrete(cmd: str) -> list[str]:
    cmd = re.sub(r"\[([^\]]+)\]", r"\1", cmd)          # optional parts are filled in
    cmd = re.sub(r"<[^>]+>", "x", cmd)                   # placeholders
    cmd = re.sub(r"\b0-5\b", "1", cmd)
    cmd = re.sub(r"--(tasks|depth|workstreams|files|tokens) [NDWF]\b", r"--\1 1", cmd)
    cmd = re.sub(r"(\w+)\|\w+(\|\w+)*", r"\1", cmd)       # start|done|fail -> start
    cmd = cmd.replace("...", "y")
    return shlex.split(cmd)[1:]


def test_skill_has_commands():
    assert len(_commands()) >= 12


def test_readme_quickstart_is_checked():
    assert sum(c.startswith("agentos agent admit") for c in _commands(README)) == 1
    assert len(_commands(README)) >= 10


def test_the_guides_show_commands():
    assert all(len(_commands(g)) >= 5 for g in GUIDES)


@pytest.mark.parametrize("cmd", _commands() + _commands(README) + [c for g in GUIDES for c in _commands(g)])
def test_skill_command_parses(cmd):
    argv = _concrete(cmd)
    if argv[-1:] == ["x"] and argv[:2] == ["agent", "transition"]:
        argv[-1] = "RUNNING"
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        if argv == ["--version"] and exc.code == 0:
            return
        pytest.fail(f"skill command does not parse: {cmd!r} -> {argv} (exit {exc.code})")
    assert getattr(args, "func", None), f"incomplete command in skill: {cmd!r}"


@pytest.mark.parametrize("doc", [SKILL, README])
def test_skill_score_keys_are_real(doc):
    keys = re.findall(r"--score (\w+)=", doc.read_text(encoding="utf-8"))
    assert keys and set(keys) <= set(WEIGHTS)
