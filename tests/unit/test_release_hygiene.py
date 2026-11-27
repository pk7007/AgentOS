"""Checks that keep the release honest: every test the audit cites as evidence exists, every locked
dependency has a licence AgentOS can ship with, and the lock satisfies the version ranges pyproject.toml
declares, so a reinstall from the lock gets what the package says it needs."""

import ast
import re
import tomllib
from importlib import metadata
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tests"
SUITES = "unit|integration|security|resilience|concurrency|live"
CITE = re.compile(rf"`(?:((?:{SUITES})/test_\w+\.py)(?:::(\w+\*?))?|::(\w+\*?))`")
ALLOWED_LICENCES = ("MIT", "BSD", "Apache", "PSF", "Python Software Foundation", "ISC")


def _test_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _citations(text: str) -> list[tuple[str | None, str | None, int]]:
    """(file or None, test or None, line) for every cited test. A bare `::name` belongs to a file the
    section names earlier, so it is looked up across the test tree; `name_*` stands for a family."""
    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for m in CITE.finditer(line):
            out.append((m.group(1), m.group(2), lineno) if m.group(1) else (None, m.group(3), lineno))
    return out


def _found(name: str, names: set[str]) -> bool:
    return any(n.startswith(name[:-1]) for n in names) if name.endswith("*") else name in names


def _unresolved(cited) -> list[str]:
    every = set().union(*(_test_names(p) for p in TESTS.rglob("test_*.py")))
    missing = []
    for file, name, lineno in cited:
        if file and not (TESTS / file).exists():
            missing.append(f"line {lineno}: {file}")
        elif name and not _found(name, _test_names(TESTS / file) if file else every):
            missing.append(f"line {lineno}: {file or ''}::{name}")
    return missing


def test_every_test_the_audit_cites_exists():
    cited = _citations((ROOT / "reports" / "AUDIT.md").read_text(encoding="utf-8"))
    assert len(cited) > 300
    assert _unresolved(cited) == [], "the audit cites tests that do not exist"


@pytest.mark.parametrize("report", ["PHASE9_SCORES.md", "PHASE9_DELIVERABLES.md", "COMPATIBILITY.md"])
def test_every_test_the_other_reports_cite_exists(report):
    path = ROOT / "reports" / report
    assert _unresolved(_citations(path.read_text(encoding="utf-8"))) == [], f"{report} cites a missing test"


def test_the_citation_check_catches_a_planted_missing_test():
    text = ("| row | `unit/test_gen.py::test_no_such_thing` `::test_codex_snippet_limits` `::test_nowhere_*`"
            " `unit/test_gone.py` `unit/test_gen.py::test_host_profile_*` |")
    cited = _citations(text)
    assert [c[:2] for c in cited] == [("unit/test_gen.py", "test_no_such_thing"), (None, "test_codex_snippet_limits"),
                                      (None, "test_nowhere_*"), ("unit/test_gone.py", None),
                                      ("unit/test_gen.py", "test_host_profile_*")]
    assert _unresolved(cited) == ["line 1: unit/test_gen.py::test_no_such_thing", "line 1: ::test_nowhere_*",
                                  "line 1: unit/test_gone.py"]


LOCK = (ROOT / "requirements-lock.txt").read_text(encoding="utf-8")


def _locked(text: str = LOCK) -> dict[str, str]:
    pins = re.findall(r"^([A-Za-z0-9_.\-]+)==([^\s\\]+)", text, re.MULTILINE)
    return {canonicalize_name(n): v for n, v in pins}


def _licence_terms(meta) -> list[str]:
    """The licences a package names: its SPDX expression, else a short License field, else its classifiers."""
    if expr := (meta.get("License-Expression") or "").strip():
        return [w for w in re.split(r"\s+(?:OR|AND|WITH)\s+|[()]", expr) if w.strip()]
    field = (meta.get("License") or "").strip()
    if field and len(field) < 80 and "\n" not in field:
        return [w for w in re.split(r"\s+(?:OR|AND|WITH)\s+|[()]", field) if w.strip()]
    return [c.split("::")[-1].strip() for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]


def _allowed(terms: list[str]) -> bool:
    """Every licence named must be on the allowlist; one copyleft, proprietary or unknown name refuses."""
    copyleft = re.compile(r"\b(A?GPL|LGPL|SSPL|EUPL|CC-BY-NC)", re.IGNORECASE)
    return bool(terms) and all(
        not copyleft.search(t) and "proprietary" not in t.lower()
        and any(a.lower() in t.lower() for a in ALLOWED_LICENCES) for t in terms)


@pytest.mark.parametrize("meta, ok", [
    ({"License-Expression": "MIT"}, True), ({"License-Expression": "Apache-2.0 OR BSD-2-Clause"}, True),
    ({"Classifier": ["License :: OSI Approved :: BSD License"]}, True), ({"License": "PSF-2.0"}, True),
    ({"License-Expression": "GPL-3.0-only"}, False), ({"License-Expression": "MIT AND GPL-2.0"}, False),
    ({"License-Expression": "Proprietary AND MIT"}, False),
    ({"License-Expression": "LicenseRef-Proprietary AND BSD-3-Clause"}, False),
    ({"License-Expression": "LicenseRef-Custom"}, False), ({}, False),
    ({"Classifier": ["License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)"]}, False),
])
def test_the_licence_rule_refuses_copyleft_proprietary_and_unknown_licences(meta, ok):
    class Meta(dict):
        def get_all(self, key):
            return self.get(key)

    assert _allowed(_licence_terms(Meta(meta))) is ok


@pytest.mark.parametrize("name", sorted(_locked()))
def test_every_locked_dependency_has_an_allowed_licence(name):
    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        pytest.skip(f"{name} is not installed here (a platform-specific dependency)")
    assert dist.version == _locked()[name], f"{name} {dist.version} is installed, not the locked {_locked()[name]}"
    terms = _licence_terms(dist.metadata)
    assert _allowed(terms), f"{name}: {terms or 'no licence'}"


def _range_problems(declared: list[str], locked: dict[str, str]) -> list[str]:
    problems = []
    for spec in declared:
        req = Requirement(spec)
        version = locked.get(canonicalize_name(req.name))
        if version is None:
            problems.append(f"{req.name} is not locked")
        elif not req.specifier.contains(version, prereleases=True):
            problems.append(f"{req.name}=={version} is outside {req.specifier}")
    return problems


def test_the_lock_satisfies_the_declared_ranges():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    declared = list(project["dependencies"]) + [d for group in project["optional-dependencies"].values()
                                                for d in group]
    assert _range_problems(declared, _locked()) == []


def test_the_range_check_catches_a_planted_mismatch():
    planted = _locked("pydantic==3.1.0 \\\n    --hash=sha256:" + "0" * 64 + "\n")
    assert _range_problems(["pydantic>=2.7,<3", "ruff>=0.6"], planted) == [
        "pydantic==3.1.0 is outside <3,>=2.7", "ruff is not locked"]


def test_the_hash_check_catches_a_planted_unhashed_pin():
    from tests.unit import test_architecture

    planted = LOCK + "requests==2.32.0\n"
    original = test_architecture.ROOT

    class Root:
        def __truediv__(self, name):
            return _Planted(planted) if name == "requirements-lock.txt" else original / name

    class _Planted:
        def __init__(self, text):
            self.text = text

        def read_text(self, encoding=None):
            return self.text

    test_architecture.ROOT = Root()
    try:
        with pytest.raises(AssertionError, match="requests has no sha256 hash"):
            test_architecture.test_every_locked_dependency_is_pinned_with_hashes()
    finally:
        test_architecture.ROOT = original
