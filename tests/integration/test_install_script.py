"""End-to-end check of scripts/install.ps1 and scripts/uninstall.ps1 in a throwaway AGENTOS_HOME.

-NoPath keeps the user's PATH untouched. The install does a real `pip install -e` (uses the pip cache).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="PowerShell installer is Windows-only")


def _ps(script: str, *args: str, env=None) -> subprocess.CompletedProcess:
    return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                           str(ROOT / "scripts" / script), *args],
                          capture_output=True, text=True, timeout=900, env=env, check=False)


def _env(home: Path) -> dict:
    env = dict(os.environ)
    env.pop("AGENTOS_HOME", None)
    env["AGENTOS_ACTOR"] = "installer-test"
    return env


def test_dry_run_changes_nothing(tmp_path):
    home = tmp_path / "h"
    r = _ps("install.ps1", "-AgentosHome", str(home), "-NoPath", env=_env(home))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "DRY RUN" in r.stdout and not home.exists()
    assert "codex plugin marketplace add" in r.stdout


def test_install_then_uninstall(tmp_path):
    home = tmp_path / "h"
    env = _env(home)
    r = _ps("install.ps1", "-Apply", "-AgentosHome", str(home), "-NoPath", "-Python", sys.executable, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    shim = home / "bin" / "agentos.cmd"
    assert shim.exists() and (home / "venv").exists()
    d = subprocess.run(["cmd", "/c", str(shim), "doctor", "--json"], capture_output=True, text=True,
                       timeout=120, env=env, check=False)
    assert d.returncode == 0, d.stdout + d.stderr
    report = json.loads(d.stdout)
    assert Path(report["home"]) == home
    checks = {c["name"]: c["status"] for c in report["checks"]}
    assert checks["database"] == "VERIFIED" and checks["audit_chain"] == "VERIFIED"
    assert (home / "state" / "agentos.db").exists()

    u = _ps("uninstall.ps1", "-Apply", "-AgentosHome", str(home), "-NoPath", env=env)
    assert u.returncode == 0, u.stdout + u.stderr
    assert not (home / "venv").exists() and not shim.exists()
    assert (home / "state" / "agentos.db").exists()


def test_uninstall_purge_keeps_final_backup(tmp_path):
    import sqlite3

    home = tmp_path / "h"
    env = _env(home)
    r = _ps("install.ps1", "-Apply", "-AgentosHome", str(home), "-NoPath", "-Python", sys.executable, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    u = _ps("uninstall.ps1", "-Apply", "-PurgeState", "-AgentosHome", str(home), "-NoPath", env=env)
    assert u.returncode == 0, u.stdout + u.stderr
    assert not (home / "state").exists() and not (home / "venv").exists()
    finals = list(home.glob("agentos-final-*.db"))
    assert len(finals) == 1
    c = sqlite3.connect(finals[0])
    try:
        assert c.execute("SELECT COUNT(*) FROM events").fetchone()[0] >= 1
    finally:
        c.close()


def test_uninstall_dry_run_changes_nothing(tmp_path):
    home = tmp_path / "h"
    (home / "venv").mkdir(parents=True)
    r = _ps("uninstall.ps1", "-PurgeState", "-AgentosHome", str(home), "-NoPath", env=_env(home))
    assert r.returncode == 0 and "DRY RUN" in r.stdout and (home / "venv").exists()


def test_installer_rejects_old_python(tmp_path):
    fake = tmp_path / "oldpy.cmd"
    fake.write_text("@echo 3.9\n")
    r = _ps("install.ps1", "-Apply", "-AgentosHome", str(tmp_path / "h"), "-NoPath", "-Python", str(fake),
            env=_env(tmp_path))
    assert r.returncode == 1 and "3.11" in (r.stdout + r.stderr)
    assert not (tmp_path / "h" / "venv").exists()
