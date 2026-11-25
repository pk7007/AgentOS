"""Live check: a real Codex session follows the agentos skill and its actions land in the audit log.

Runs only with `python -m pytest -m live`. It starts one `codex exec` session, which uses the
signed-in Codex account's quota, so run it only with the owner's go-ahead.
Everything it writes stays inside a temporary repository (AGENTOS_HOME lives there too, so the
workspace-write sandbox allows it). The owner's own ~/.agentos is never touched.
"""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import make_repo

ROOT = Path(__file__).resolve().parents[2]
pytestmark = [pytest.mark.live,
              pytest.mark.skipif(shutil.which("codex") is None, reason="codex CLI not on PATH")]

PROMPT = """Use the agentos skill in .agents/skills/agentos/SKILL.md. Run these with the `agentos` command,
passing --json and --host codex where accepted:
1. agentos status
2. add a task titled "smoke task"
3. admit one worker for it with the researcher template
4. move that instance to RUNNING, then COMPLETED
Report the instance id. Do not edit any files."""


def _agentos(env, *args):
    exe = Path(sys.executable).with_name("agentos.exe" if os.name == "nt" else "agentos")
    return subprocess.run([str(exe), *args], env=env, capture_output=True, text=True, timeout=120, check=False)


def test_codex_follows_skill(tmp_path):
    repo = make_repo(tmp_path / "smoke")
    env = dict(os.environ, AGENTOS_HOME=str(repo / ".agentos-home"), AGENTOS_ACTOR="codex-smoke")
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    for args in (["init"], ["template", "seed"], ["project", "activate", str(repo)]):
        r = _agentos(env, *args)
        assert r.returncode == 0, r.stderr
    skill = repo / ".agents" / "skills" / "agentos"
    skill.mkdir(parents=True)
    shutil.copy(ROOT / "plugins" / "codex" / "skills" / "agentos" / "SKILL.md", skill / "SKILL.md")

    out = subprocess.run(["codex", "exec", "--skip-git-repo-check", "-s", "workspace-write", "-C", str(repo),
                          PROMPT], env=env, capture_output=True, text=True, timeout=900, check=False,
                         shell=os.name == "nt")
    assert out.returncode == 0, out.stdout[-2000:] + out.stderr[-2000:]

    verify = _agentos(env, "audit", "verify", "--json")
    assert verify.returncode == 0 and json.loads(verify.stdout)["ok"] is True
    db = sqlite3.connect(repo / ".agentos-home" / "state" / "agentos.db")
    try:
        kinds = [k for (k,) in db.execute("SELECT kind FROM events ORDER BY seq")]
        states = [s for (s,) in db.execute("SELECT state FROM agent_instances")]
    finally:
        db.close()
    assert "agent.admitted" in kinds
    assert states == ["COMPLETED"]
