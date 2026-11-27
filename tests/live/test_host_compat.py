"""Live compatibility with the host CLIs installed on this machine. No model session is started and no
quota is used: each host only reads and validates the plugin AgentOS installed. Opt-in: `pytest -m live`."""

import os
import shlex
import shutil
import subprocess

import pytest

from agentos import adapters, db
from agentos.errors import UsageError

pytestmark = pytest.mark.live


@pytest.fixture
def conn(home):
    c = db.connect()
    db.migrate(c)
    yield c
    c.close()


def _run(argv, env=None):
    return subprocess.run(argv, capture_output=True, text=True, timeout=120, env=env, check=False)


def test_codex_accepts_the_installed_plugin(conn, tmp_path):
    exe = shutil.which("codex")
    if not exe:
        pytest.skip("codex CLI not on PATH")
    r = adapters.install(conn, "codex", "live", tmp_path / "codex-plugin")
    assert r["host_version"] and r["host_version"].startswith("codex")
    (tmp_path / "codex-home").mkdir()
    env = os.environ | {"CODEX_HOME": str(tmp_path / "codex-home")}
    added = _run([exe, "plugin", "marketplace", "add", r["dest"]], env)
    assert added.returncode == 0, added.stderr
    listed = _run([exe, "plugin", "marketplace", "list"], env)
    assert "agentos" in listed.stdout
    assert adapters.drift(conn, "codex")["status"] == "in_sync"


def test_the_second_host_validates_the_installed_plugin(conn, tmp_path):
    try:
        a = adapters.resolve("cc")
    except UsageError as exc:  # no profile on this machine
        pytest.skip(f"second host not configured: {exc}")
    template = a.profile.get("validate_command")
    if not template or not a.executable or not shutil.which(a.executable):
        pytest.skip("the profile names no validate_command, or its CLI is not installed")
    r = adapters.install(conn, "cc", "live", tmp_path / "cc-plugin")
    argv = [x.replace("{exe}", a.executable).replace("{dest}", r["dest"]) for x in shlex.split(template)]
    out = _run(argv)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "warning" not in (out.stdout + out.stderr).lower()
