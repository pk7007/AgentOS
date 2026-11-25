"""Generators that turn the vendor-neutral definitions into host plugin files."""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from agentos.errors import IntegrityError, UsageError
from agentos.templates import AgentTemplate, load_definitions
from agentos.util import load_toml

MANIFEST = ".agentos-gen.json"


@dataclass
class GenResult:
    written: list[Path] = field(default_factory=list)
    skipped_modified: list[Path] = field(default_factory=list)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Writer:
    """Writes generated files, but never overwrites a file a human changed (unless force)."""

    def __init__(self, out_dir: Path, force: bool = False):
        self.out = Path(out_dir).resolve()
        self.force = force
        self.result = GenResult()
        mf = self.out / MANIFEST
        self.known: dict[str, str] = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {}
        self.new: dict[str, str] = dict(self.known)

    def write(self, rel: str, text: str) -> None:
        path = (self.out / rel).resolve()
        if self.out not in path.parents:
            raise IntegrityError(f"generated path escapes the output directory: {rel}")
        data = text.encode("utf-8")
        if path.exists() and not self.force:
            current = _sha(path.read_bytes())
            if self.known.get(rel) != current:
                self.result.skipped_modified.append(path)
                return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.new[rel] = _sha(data)
        self.result.written.append(path)

    def finish(self) -> GenResult:
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / MANIFEST).write_text(json.dumps(self.new, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return self.result


def load_plugin_meta(defs_dir: Path) -> dict:
    path = Path(defs_dir) / "plugin.toml"
    if not path.exists():
        raise UsageError(f"missing {path}")
    return load_toml(path)


def load_agents(defs_dir: Path) -> list[AgentTemplate]:
    return load_definitions(Path(defs_dir) / "agents")


def skill_text(defs_dir: Path) -> str:
    path = Path(defs_dir) / "skills" / "agentos" / "SKILL.md"
    if not path.exists():
        raise UsageError(f"missing {path}")
    return path.read_text(encoding="utf-8")
