"""Add sha256 hashes to requirements-lock.txt for every published file of each pinned version.

Run after changing a pin:  python scripts/lock_hashes.py
The hashes come from PyPI's JSON API. With them, `pip install --require-hashes -r requirements-lock.txt`
refuses any file whose bytes differ from what was published when the lock was made."""

import json
import re
import sys
import urllib.request
from pathlib import Path

LOCK = Path(__file__).resolve().parents[1] / "requirements-lock.txt"
PIN = re.compile(r"^([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+-]+)")


def hashes(name: str, version: str) -> list[str]:
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    with urllib.request.urlopen(url, timeout=30) as r:
        files = json.load(r)["urls"]
    found = sorted({f["digests"]["sha256"] for f in files})
    if not found:
        sys.exit(f"no files published for {name}=={version}")
    return found


def main() -> int:
    out = ["# Locked, hash-checked dependencies. Regenerate with: python scripts/lock_hashes.py"]
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        m = PIN.match(line.strip())
        if not m:
            continue
        name, version = m.groups()
        digests = hashes(name, version)
        out.append(f"{name}=={version} \\")
        out += [f"    --hash=sha256:{d}" + (" \\" if i < len(digests) - 1 else "") for i, d in enumerate(digests)]
    LOCK.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {LOCK} ({sum(1 for x in out if '==' in x)} packages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
