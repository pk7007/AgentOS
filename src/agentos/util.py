"""Small shared helpers."""

import hashlib
import json
import uuid
from datetime import UTC, datetime


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_json(obj) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_toml(path) -> dict:
    """Read a TOML file, tolerating the BOM that Windows editors and PowerShell 5.1 add."""
    import tomllib
    from pathlib import Path

    from agentos.errors import UsageError

    try:
        return tomllib.loads(Path(path).read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise UsageError(f"cannot read {path}: {exc.strerror or exc}") from exc
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise UsageError(f"invalid TOML in {path}: {exc}") from exc
