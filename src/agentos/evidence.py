"""Evidence that AgentOS itself observed: it runs the command and records what really happened.

A host can still choose *which* command to run, but it cannot invent the result. Every record keeps
the exact argv, the working directory, the exit code, hashes of the full output, a redacted tail
and the git HEAD at the time, so a reviewer can see what the evidence actually proves.
"""

import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

from pydantic import BaseModel

from agentos import audit, projects
from agentos.db import write_tx
from agentos.errors import NotFound, PolicyDenied, UsageError
from agentos.redact import redact
from agentos.util import new_id, now_iso

TAIL_CHARS = 4000
DEFAULT_TIMEOUT_S = 900

# Commands that reach outside this machine or publish something. A check that grades work never needs
# them, so `evidence run` refuses them unless the owner confirms. This is a boundary for the obvious
# cases, not a sandbox: a test script can still open a connection itself.
EXTERNAL_PROGRAMS = {"curl", "wget", "ssh", "scp", "sftp", "ftp", "nc", "ncat", "netcat", "telnet", "rsync",
                     "gh", "twine", "invoke-webrequest", "iwr", "invoke-restmethod", "irm",
                     # package runners fetch the package they are asked to run
                     "npx", "uvx", "pipx", "bunx", "pnpx"}
EXTERNAL_SUBCOMMANDS = {"git": {"push", "fetch", "pull", "clone", "remote", "send-email", "submodule", "ls-remote"},
                        "poetry": {"install", "add", "update", "lock", "publish"},
                        "conda": {"install", "create", "update"}, "mamba": {"install", "create", "update"},
                        "winget": {"install", "upgrade"}, "choco": {"install", "upgrade"}, "scoop": {"install", "update"},
                        "brew": {"install", "upgrade", "update"}, "apt": {"install", "update", "upgrade"},
                        "apt-get": {"install", "update", "upgrade"}, "go": {"get", "install", "mod"},
                        "gem": {"install", "push"}, "dotnet": {"add", "restore", "nuget"},
                        "pip": {"install", "download", "upload"}, "pip3": {"install", "download", "upload"},
                        "uv": {"pip", "add", "sync"}, "npm": {"publish", "login", "adduser", "install", "ci", "i"},
                        "yarn": {"publish", "add", "install"}, "pnpm": {"publish", "add", "install"},
                        "cargo": {"publish", "login", "install"}, "docker": {"push", "pull", "login"}}
# programs that run another command given as an argument: the words they are given are looked at too
WRAPPERS = {"cmd", "bash", "sh", "zsh", "dash", "powershell", "pwsh", "env", "python", "python3", "py",
            "node", "deno", "bun", "ruby", "perl", "start", "call"}


def _prog(word: str) -> str:
    prog = re.split(r"[\\/]", word.strip().strip('"\''))[-1].lower()  # either separator, whatever the OS
    for suffix in (".exe", ".cmd", ".bat", ".ps1"):
        prog = prog.removesuffix(suffix)
    return re.sub(r"^(pip|python)\d+(\.\d+)*$", r"\1", prog)  # pip3.12 is pip, python3.11 is python


def _direct(prog: str, rest: list[str]) -> str | None:
    if prog in EXTERNAL_PROGRAMS:
        return prog
    # any later word counts, not just the first: global options such as `git -C DIR` come before it, and
    # a false alarm only means asking the owner
    sub = next((a.lower() for a in rest if a.lower() in EXTERNAL_SUBCOMMANDS.get(prog, ())), None)
    return f"{prog} {sub}" if sub else None


def external_action(argv: list[str]) -> str | None:
    """The part of `argv` that reaches outside this machine, or None. A shell or interpreter at the front
    (`cmd /c`, `bash -c`, `python -m pip`) is looked through: each word it is given is checked as a command
    of its own."""
    if not argv:
        return None
    prog = _prog(argv[0])
    if hit := _direct(prog, argv[1:]):
        return hit
    if prog in WRAPPERS or prog.startswith("python"):
        words = [w for a in argv[1:] for w in re.split(r"[\s;|&()'\"`]+", a) if w]
        for i, w in enumerate(words):
            if hit := _direct(_prog(w), words[i + 1:i + 5]):
                return hit
    return None


class Evidence(BaseModel):
    id: str
    project_id: str
    command: list[str]
    cwd: str
    exit_code: int
    timed_out: bool
    stdout_sha256: str
    stderr_sha256: str
    output_tail: str
    git_head: str | None
    started_at: str
    finished_at: str
    duration_ms: int
    actor: str


def _row(row) -> Evidence:
    d = dict(row)
    d["command"] = json.loads(d["command"])
    d["timed_out"] = bool(d["timed_out"])
    return Evidence(**d)


def get(conn: sqlite3.Connection, evidence_id: str) -> Evidence:
    row = conn.execute("SELECT * FROM evidence WHERE id=?", (evidence_id,)).fetchone()
    if not row:
        raise NotFound(f"evidence not found: {evidence_id}")
    return _row(row)


def read(conn: sqlite3.Connection, evidence_id: str, project_id: str) -> Evidence:
    ev = get(conn, evidence_id)
    if ev.project_id != project_id:
        raise PolicyDenied("evidence belongs to another project", reasons=["cross_project"])
    return ev


def _git_head(cwd: Path) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(cwd), "rev-parse", "HEAD"], capture_output=True, text=True,
                           timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return (r.stdout.strip() or None) if r.returncode == 0 else None


def _resolve(argv: list[str]) -> list[str]:
    exe = shutil.which(argv[0])
    if exe and Path(exe).suffix.lower() in (".cmd", ".bat"):
        return ["cmd", "/c", exe, *argv[1:]]
    return [exe or argv[0], *argv[1:]]


def run(conn: sqlite3.Connection, project_id: str, argv: list[str], actor: str,
        timeout_s: int = DEFAULT_TIMEOUT_S, owner=None) -> Evidence:
    """Run `argv` (no shell) in the project's repository and record the observed result. A command that
    reaches outside this machine (`external_action`) is refused unless the owner confirmed it; the
    refusal is recorded."""
    from agentos.governance import is_owner

    if not argv or not argv[0].strip():
        raise UsageError("evidence run needs a command, e.g. agentos evidence run -- pytest -q")
    project = projects.get_project(conn, project_id)
    outside = external_action(argv)
    if outside and not is_owner(owner):
        with write_tx(conn):
            audit.append_event(conn, "evidence.refused", actor, {"command": argv, "external": outside}, project_id)
        raise PolicyDenied(f"`{outside}` reaches outside this machine; a check does not need it, and running it"
                           " needs the owner", reasons=["external_action"])
    cwd = Path(project.path)
    started, t0 = now_iso(), time.monotonic()
    timed_out = False
    try:
        r = subprocess.run(_resolve(argv), cwd=cwd, capture_output=True, timeout=timeout_s, check=False)
        out, err, code = r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired as exc:
        out, err, code, timed_out = exc.stdout or b"", exc.stderr or b"", -1, True
    except OSError as exc:
        out, err, code = b"", str(exc).encode(), 127
    duration = int((time.monotonic() - t0) * 1000)
    text = (out + b"\n" + err).decode("utf-8", errors="replace").strip()
    tail, _ = redact(text[-TAIL_CHARS:])
    eid = new_id("evd")
    with write_tx(conn):
        conn.execute(
            "INSERT INTO evidence(id, project_id, command, cwd, exit_code, timed_out, stdout_sha256, stderr_sha256,"
            " output_tail, git_head, started_at, finished_at, duration_ms, actor) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (eid, project_id, json.dumps(argv), str(cwd), code, int(timed_out), hashlib.sha256(out).hexdigest(),
             hashlib.sha256(err).hexdigest(), tail, _git_head(cwd), started, now_iso(), duration, actor))
        audit.append_event(conn, "evidence.recorded", actor, {
            "evidence_id": eid, "command": argv, "exit_code": code, "timed_out": timed_out}, project_id)
    return get(conn, eid)
