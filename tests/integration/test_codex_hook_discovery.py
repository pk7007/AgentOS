"""The real Codex CLI discovers the plugin's hooks. Uses no model and no quota: it installs the
generated plugin into a throwaway CODEX_HOME and asks the local app-server (`hooks/list`) what it
found. Skipped when the Codex CLI is not installed (for example on CI)."""

import json
import os
import queue
import shutil
import subprocess
import threading
import time

import pytest

from agentos.gen import codex as gen_codex
from tests.conftest import make_repo

CODEX = shutil.which("codex.cmd") or shutil.which("codex")
pytestmark = pytest.mark.skipif(CODEX is None, reason="codex CLI not on PATH")
DEFS = __import__("pathlib").Path(__file__).resolve().parents[2] / "definitions"


def _codex(env, *args):
    return subprocess.run([CODEX, *args], env=env, capture_output=True, text=True, timeout=180, check=False)


def _hooks_list(env, cwd) -> dict:
    p = subprocess.Popen([CODEX, "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, env=env, cwd=cwd)
    lines: queue.Queue = queue.Queue()
    threading.Thread(target=lambda: [lines.put(x) for x in p.stdout], daemon=True).start()

    def send(obj):
        p.stdin.write((json.dumps(obj) + "\n").encode())
        p.stdin.flush()

    def wait_for(msg_id, deadline):
        while time.monotonic() < deadline:
            try:
                msg = json.loads(lines.get(timeout=1))
            except queue.Empty:
                continue
            except ValueError:
                continue
            if msg.get("id") == msg_id:
                return msg
        raise AssertionError(f"no app-server reply to request {msg_id}")

    try:
        deadline = time.monotonic() + 90
        send({"method": "initialize", "id": 1, "params": {"clientInfo": {"name": "agentos-test", "version": "0"}}})
        wait_for(1, deadline)
        send({"method": "initialized"})
        send({"method": "hooks/list", "id": 2, "params": {"cwds": [str(cwd)]}})
        return wait_for(2, deadline)
    finally:
        p.kill()
        p.wait(timeout=30)


def test_codex_discovers_the_plugin_hooks(tmp_path):
    plugin = tmp_path / "plugin"
    gen_codex.generate(DEFS, plugin)
    (tmp_path / "codex-home").mkdir()
    env = dict(os.environ, CODEX_HOME=str(tmp_path / "codex-home"))
    for args in (["plugin", "marketplace", "add", str(plugin)], ["plugin", "add", "agentos@agentos"]):
        r = _codex(env, *args)
        assert r.returncode == 0, r.stderr
    repo = make_repo(tmp_path / "repo")
    reply = _hooks_list(env, repo)
    entry = reply["result"]["data"][0]
    assert entry["errors"] == [] and entry["warnings"] == []
    ours = {h["eventName"]: h for h in entry["hooks"] if h.get("pluginId") == "agentos@agentos"}
    assert set(ours) == {"preToolUse", "subagentStart", "subagentStop"}
    assert ours["preToolUse"]["matcher"] == "^(Agent|spawn_agent)$"
    assert all(h["command"] == "agentos hook run codex" for h in ours.values())
    # Codex runs no plugin hook until the owner reviews and trusts it (/hooks).
    assert {h["trustStatus"] for h in ours.values()} == {"untrusted"}
