"""Native host adapters: install the generated plugin for a host, detect drift, roll back, write a
concise bootstrap block into a project, and check that AgentOS coexists with other plugins.

One set of definitions (`definitions/`) feeds every host. The Codex adapter's file names ship with
AgentOS. Any other host's file names come from a profile the owner keeps on their machine
(`~/.agentos/hosts/<host>.toml`, or `hosts/<host>.local.toml` in a checkout), so no host-specific
names have to live in this repository.

AgentOS never edits a host's own configuration. `install` copies the plugin into a folder AgentOS
owns and prints the one command that registers it with the host; every install keeps a backup, so
it can be rolled back."""

import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from pydantic import BaseModel

from agentos import audit, paths
from agentos.db import write_tx
from agentos.errors import NotFound, PolicyDenied, UsageError
from agentos.util import load_toml, new_id, now_iso

REPO = Path(__file__).resolve().parents[2]
DEFS = REPO / "definitions"
BEGIN, END = "<!-- agentos:begin -->", "<!-- agentos:end -->"
HOOK_EVENTS = ("PreToolUse", "SubagentStart", "SubagentStop")
MAX_SCAN_FILES = 20000

BOOTSTRAP = """## AgentOS

This repository is coordinated by AgentOS (the local `agentos` command). Follow the `agentos` skill.

- Start with `agentos status --json`; resume an open handover with `agentos handover resume <id> --host {host} --json`.
- Ask `agentos agent admit` before starting any worker. If it is denied, do not start it.
- Grade work with `agentos eval record` citing `agentos evidence run` results. Never grade your own work.
- Before you stop mid-task, write `agentos handover create --objective "..." --next "..." --host {host} --json`.
- Owner-only actions need the human owner at a real terminal; ask, don't work around them."""


class Adapter(BaseModel):
    id: str
    profile: dict
    profile_path: str | None
    executable: str | None
    instructions_file: str
    spawn_tools: list[str]
    plugins_dir: str | None
    agents_home: str | None
    register_hint: str | None
    capabilities: dict


def _profile_file(host: str, explicit: Path | None) -> Path | None:
    if explicit:
        if not Path(explicit).exists():
            raise UsageError(f"host profile not found: {explicit}")
        return Path(explicit)
    for candidate in (paths.agentos_home() / "hosts" / f"{host}.toml", REPO / "hosts" / f"{host}.local.toml"):
        if candidate.exists():
            return candidate
    return None


def resolve(host: str, profile: Path | None = None) -> Adapter:
    from agentos.runtime import profile as runtime_profile

    rp = runtime_profile(host)  # unknown hosts are refused here
    path = _profile_file(host, profile)
    prof = load_toml(path) if path else {}
    if host == "codex":
        instructions, exe = prof.get("instructions_file", "AGENTS.md"), prof.get("executable", "codex")
        hint = prof.get("register_hint", "codex plugin marketplace add {dest}")
        hooks = True
    else:
        if path is None:
            raise UsageError(f"the {host} adapter needs a host profile at "
                             f"{paths.agentos_home() / 'hosts' / (host + '.toml')} (see docs/HOST_PROFILE.md)")
        from agentos.gen.host import load_profile

        load_profile(path)
        instructions, exe, hint = prof["instructions_file"], prof.get("executable"), prof.get("register_hint")
        hooks = bool(prof.get("hooks_file"))
        if hooks and prof.get("runtime_host") != host:
            raise UsageError(f"profile {path}: set runtime_host = \"{host}\" so its hooks call `agentos hook run {host}`")
    caps = {"skills": True, "agents": True, "hooks": hooks, "bootstrap": True,
            "hook_events": list(HOOK_EVENTS) if hooks else [], "spawn_tools": sorted(rp.spawn_tools)}
    return Adapter(id=host, profile=prof, profile_path=str(path) if path else None, executable=exe,
                   instructions_file=instructions, spawn_tools=sorted(rp.spawn_tools),
                   plugins_dir=prof.get("plugins_dir"), agents_home=prof.get("agents_home"),
                   register_hint=hint, capabilities=caps)


def generate(a: Adapter, out: Path, force: bool = False, defs: Path = DEFS):
    if a.id == "codex":
        from agentos.gen import codex

        return codex.generate(defs, out, force=force)
    from agentos.gen import host

    return host.generate(defs, Path(a.profile_path), out, force=force)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def tree(root: Path) -> dict[str, str]:
    root = Path(root)
    if not root.exists():
        return {}
    return {p.relative_to(root).as_posix(): _sha(p.read_bytes()) for p in sorted(root.rglob("*")) if p.is_file()}


def defs_hash(defs: Path = DEFS) -> str:
    h = hashlib.sha256()
    for rel, digest in tree(defs).items():
        h.update(f"{rel}\0{digest}\n".encode())
    return h.hexdigest()


def host_version(a: Adapter) -> str | None:
    """The host CLI's own `--version` output, or None when it is not installed."""
    exe = shutil.which(a.executable) if a.executable else None
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    line = (out.stdout or out.stderr).strip().splitlines()
    return line[0][:120] if out.returncode == 0 and line else None


def _row(conn, host: str):
    return conn.execute("SELECT * FROM host_installs WHERE host=? AND status='active'"
                        " ORDER BY installed_at DESC, rowid DESC LIMIT 1", (host,)).fetchone()


def installed(conn: sqlite3.Connection, host: str) -> dict | None:
    row = _row(conn, host)
    return None if row is None else dict(row) | {"files": json.loads(row["files"])}


def history(conn: sqlite3.Connection, host: str | None = None) -> list[dict]:
    sql, params = "SELECT id, host, dest, defs_hash, host_version, status, installed_at, actor FROM host_installs", []
    if host:
        sql += " WHERE host=?"
        params.append(host)
    return [dict(r) for r in conn.execute(sql + " ORDER BY installed_at, rowid", params)]


def _default_dest(host: str) -> Path:
    return paths.agentos_home() / "plugins" / host


def _staged(a: Adapter, defs: Path) -> tuple[Path, dict[str, str]]:
    stage = Path(tempfile.mkdtemp(prefix=f"agentos-{a.id}-"))
    generate(a, stage, force=True, defs=defs)
    return stage, tree(stage)


def install(conn: sqlite3.Connection, host: str, actor: str, dest: Path | None = None,
            profile: Path | None = None, defs: Path = DEFS) -> dict:
    """Generate the plugin and copy it to `dest` (default `~/.agentos/plugins/<host>`). Whatever is
    there from the previous install is backed up first, hand edits included."""
    a = resolve(host, profile)
    dest = Path(dest or _default_dest(host)).resolve()
    prev = installed(conn, host)
    same_place = prev is not None and Path(prev["dest"]).resolve() == dest
    if dest.exists() and any(dest.iterdir()) and not same_place:
        raise PolicyDenied(f"{dest} is not empty and holds no AgentOS install; choose an empty folder",
                           reasons=["dest_not_empty"])
    stage, staged = _staged(a, defs)
    iid = new_id("hin")
    backup, modified = None, []
    try:
        if same_place:
            backup = paths.agentos_home() / "host-backups" / host / iid
            for rel, digest in prev["files"].items():
                src = dest / rel
                if src.exists():
                    if _sha(src.read_bytes()) != digest:
                        modified.append(rel)
                    (backup / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, backup / rel)
            for rel in prev["files"]:
                if rel not in staged and (dest / rel).exists():
                    (dest / rel).unlink()
        for rel in staged:
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(stage / rel, dest / rel)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    version, digest = host_version(a), defs_hash(defs)
    with write_tx(conn):
        if prev:
            conn.execute("UPDATE host_installs SET status='superseded' WHERE id=?", (prev["id"],))
        conn.execute("INSERT INTO host_installs(id, host, dest, files, defs_hash, host_version, backup_dir,"
                     " previous_id, status, installed_at, actor) VALUES (?,?,?,?,?,?,?,?,'active',?,?)",
                     (iid, host, str(dest), json.dumps(staged), digest, version, str(backup) if backup else None,
                      prev["id"] if prev else None, now_iso(), actor))
        audit.append_event(conn, "host.installed", actor,
                           {"install_id": iid, "host": host, "dest": str(dest), "files": len(staged),
                            "defs_hash": digest, "host_version": version, "replaced": prev["id"] if prev else None,
                            "backed_up_modified": modified})
    return {"install_id": iid, "host": host, "dest": str(dest), "files": len(staged), "defs_hash": digest,
            "host_version": version, "backup_dir": str(backup) if backup else None,
            "backed_up_modified": modified, "capabilities": a.capabilities,
            "register": a.register_hint.format(dest=dest) if a.register_hint else None}


def drift(conn: sqlite3.Connection, host: str, profile: Path | None = None, defs: Path = DEFS) -> dict:
    """What changed since the install: files edited or deleted by hand, definitions that would now
    generate something different, and a host CLI that was updated."""
    a = resolve(host, profile)
    row = installed(conn, host)
    if row is None:
        raise NotFound(f"{host} is not installed; run: agentos host install {host}")
    dest, recorded = Path(row["dest"]), row["files"]
    missing = sorted(rel for rel in recorded if not (dest / rel).exists())
    modified = sorted(rel for rel, d in recorded.items() if (dest / rel).exists()
                      and _sha((dest / rel).read_bytes()) != d)
    stage, staged = _staged(a, defs)
    shutil.rmtree(stage, ignore_errors=True)
    stale = sorted(rel for rel in set(staged) | set(recorded) if staged.get(rel) != recorded.get(rel))
    version = host_version(a)
    host_changed = bool(version and row["host_version"] and version != row["host_version"])
    drifted = bool(missing or modified or stale or host_changed)
    actions = []
    if stale or missing:
        actions.append(f"agentos host install {host}")
    if modified:
        actions.append("your hand edits are backed up by the next install; move them into definitions/ to keep them")
    if host_changed:
        actions.append(f"the host CLI changed ({row['host_version']} -> {version}); re-check it: agentos host check {host}")
    return {"host": host, "install_id": row["id"], "dest": str(dest), "status": "drifted" if drifted else "in_sync",
            "missing": missing, "modified": modified, "stale": stale, "installed_host_version": row["host_version"],
            "host_version": version, "host_changed": host_changed, "actions": actions}


def rollback(conn: sqlite3.Connection, host: str, actor: str) -> dict:
    """Put back exactly what the previous install left, hand edits included."""
    row = installed(conn, host)
    if row is None:
        raise NotFound(f"{host} is not installed")
    if not row["previous_id"] or not row["backup_dir"] or not Path(row["backup_dir"]).exists():
        raise PolicyDenied("there is no earlier install in this folder to roll back to", reasons=["nothing_to_roll_back"])
    dest, backup = Path(row["dest"]), Path(row["backup_dir"])
    for rel in row["files"]:
        if (dest / rel).exists():
            (dest / rel).unlink()
    restored = []
    for src in sorted(backup.rglob("*")):
        if src.is_file():
            rel = src.relative_to(backup).as_posix()
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest / rel)
            restored.append(rel)
    _prune(dest)
    with write_tx(conn):
        conn.execute("UPDATE host_installs SET status='rolled_back' WHERE id=?", (row["id"],))
        conn.execute("UPDATE host_installs SET status='active' WHERE id=?", (row["previous_id"],))
        audit.append_event(conn, "host.rolled_back", actor,
                           {"host": host, "from": row["id"], "to": row["previous_id"], "restored": len(restored)})
    return {"host": host, "rolled_back": row["id"], "active": row["previous_id"], "restored": restored}


def uninstall(conn: sqlite3.Connection, host: str, actor: str, force: bool = False) -> dict:
    """Remove the installed files. Files edited by hand are kept unless `force`."""
    row = installed(conn, host)
    if row is None:
        raise NotFound(f"{host} is not installed")
    dest, removed, kept = Path(row["dest"]), [], []
    for rel, digest in row["files"].items():
        path = dest / rel
        if not path.exists():
            continue
        if _sha(path.read_bytes()) != digest and not force:
            kept.append(rel)
            continue
        path.unlink()
        removed.append(rel)
    _prune(dest)
    with write_tx(conn):
        conn.execute("UPDATE host_installs SET status='removed' WHERE id=?", (row["id"],))
        audit.append_event(conn, "host.uninstalled", actor,
                           {"host": host, "install_id": row["id"], "removed": len(removed), "kept": kept})
    return {"host": host, "removed": len(removed), "kept_modified": kept}


def _prune(root: Path) -> None:
    if not root.exists():
        return
    for d in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if not any(d.iterdir()):
            d.rmdir()


def bootstrap(conn: sqlite3.Connection, repo: Path, host: str, actor: str, remove: bool = False,
              profile: Path | None = None) -> dict:
    """Write (or remove) a short AgentOS block in the project's instructions file. Text outside the
    block is never touched."""
    from agentos.projects import project_id_for, repo_root, require_active

    a = resolve(host, profile)
    root = repo_root(Path(repo))
    project = require_active(conn, project_id_for(root))
    path = (root / a.instructions_file).resolve()
    if root.resolve() not in path.parents:
        raise PolicyDenied("instructions file must be inside the repository", reasons=["path_outside_repo"])
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", re.DOTALL)
    block = f"{BEGIN}\n{BOOTSTRAP.format(host=host)}\n{END}\n"
    if remove:
        if not pattern.search(text):
            action = "absent"
        else:
            rest = pattern.sub("", text).rstrip("\n")
            if rest.strip():
                path.write_text(rest + "\n", encoding="utf-8")
            else:
                path.unlink()
            action = "removed"
    elif pattern.search(text):
        new = pattern.sub(lambda _: block, text, count=1)
        action = "unchanged" if new == text else "updated"
        if new != text:
            path.write_text(new, encoding="utf-8")
    else:
        path.write_text((text.rstrip("\n") + "\n\n" if text.strip() else "") + block, encoding="utf-8")
        action = "added"
    if action not in ("unchanged", "absent"):
        with write_tx(conn):
            audit.append_event(conn, "host.bootstrap", actor, {"host": host, "file": a.instructions_file,
                                                               "action": action}, project.id)
    return {"host": host, "file": str(path), "action": action}


def _matches(matcher, tools: list[str]) -> bool:
    if matcher in (None, "", "*"):
        return True
    try:
        rx = re.compile(str(matcher))
    except re.error:
        return any(t in str(matcher) for t in tools)
    return any(rx.search(t) for t in tools)


def check(host: str, profile: Path | None = None, defs: Path = DEFS, exclude: Path | None = None) -> dict:
    """Coexistence with other plugins (for example ECC): hooks on the same events, agents and skills
    with the same names, and a second AgentOS install that would gate every spawn twice."""
    from agentos.gen import load_agents

    a = resolve(host, profile)
    ours = {t.id for t in load_agents(defs)}
    roots = [Path(p).expanduser() for p in (a.plugins_dir, a.agents_home) if p]
    skip = Path(exclude or _default_dest(host)).resolve()
    hooks, agents, skills, duplicates, unreadable = [], [], [], [], []
    scanned = 0
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            scanned += 1
            if scanned > MAX_SCAN_FILES:
                break
            if not path.is_file() or skip in path.resolve().parents:
                continue
            rel = str(path)
            if path.name == "hooks.json" or (path.suffix == ".json" and path.parent.name == "hooks"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8-sig"))
                except (OSError, ValueError):
                    unreadable.append(rel)
                    continue
                for event, entries in (data.get("hooks") or {}).items():
                    if event not in HOOK_EVENTS or not isinstance(entries, list):
                        continue
                    for entry in entries:
                        commands = [h.get("command", "") for h in entry.get("hooks", []) if isinstance(h, dict)]
                        if any("agentos hook run" in c for c in commands):
                            duplicates.append(rel)
                        elif event != "PreToolUse" or _matches(entry.get("matcher"), a.spawn_tools):
                            hooks.append({"file": rel, "event": event, "matcher": entry.get("matcher")})
            elif path.parent.name == "agents" and path.suffix in (".md", ".toml") and path.stem in ours:
                agents.append(path.stem)
            elif path.name == "SKILL.md" and path.parent.name == "agentos":
                skills.append(rel)
    verdict = "conflict" if duplicates else ("review" if unreadable else "compatible")
    notes = [("Every matching hook runs, and a deny from any of them blocks the call, so another plugin's "
              "hook cannot turn an AgentOS refusal into an allow.")]
    if agents:
        notes.append("Plugin agents are namespaced by plugin (agentos:<name>), so a same-named agent elsewhere "
                     "does not replace ours; a user-level agent of the same name is a different agent.")
    if duplicates:
        notes.append("A second AgentOS hook set would claim two admission tickets per spawn. Keep one install.")
    return {"host": host, "verdict": verdict, "files_scanned": min(scanned, MAX_SCAN_FILES),
            "roots": [str(r) for r in roots], "shared_hook_events": hooks,
            "same_name_agents": [{"name": n, "files": agents.count(n)} for n in sorted(set(agents))],
            "same_name_skills": skills, "duplicate_agentos_hooks": sorted(set(duplicates)),
            "unreadable": unreadable, "notes": notes}


def status(conn: sqlite3.Connection, profile_for: dict | None = None) -> list[dict]:
    """Every known host: whether an adapter is configured, its capabilities and its install."""
    from agentos.runtime import HOSTS

    out = []
    for host in sorted(HOSTS):
        try:
            a = resolve(host, (profile_for or {}).get(host))
            entry = {"host": host, "configured": True, "capabilities": a.capabilities,
                     "host_version": host_version(a), "profile": a.profile_path}
        except UsageError as exc:
            entry = {"host": host, "configured": False, "reason": str(exc)}
        row = installed(conn, host)
        entry["installed"] = {"install_id": row["id"], "dest": row["dest"], "installed_at": row["installed_at"]} \
            if row else None
        out.append(entry)
    return out
