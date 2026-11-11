"""C3 -- the command lines are the only door, and there is no database.

Read from the SOURCE, the TREE and the DEPENDENCY LIST, never from prose:

* no `import` of either module's package or of a database driver anywhere in
  the runtime package (AST -- a string scan would fire on this docstring);
* no read of the environment at all -- `os.environ`, `os.getenv`,
  `os.environb` -- so no DSN (AST);
* no `migrations/` directory in the tree;
* an empty runtime dependency list in `pyproject.toml`;
* the two console scripts are what is run, and their absence is a refusal by
  name, exit 2, before any link is read;
* the two packages installed for the tests are the commits `pyproject.toml`
  pins, read from each distribution's `direct_url.json`.

Each check has its plant. Three are string plants in `scripts/fail_controls.py`
(an import, an environment read, a driver in `dependencies`); the fourth -- a
`migrations/` directory -- is a directory, so it is planted here, in a
`finally`, against the same checker the guarantee test uses.
"""

from __future__ import annotations

import ast
import importlib.metadata as metadata
import json
import shutil
import tomllib
from pathlib import Path

import pytest

from harness import pinned_commits
from pass_billing_connector import cli, doors

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "pass_billing_connector"

FORBIDDEN_PACKAGES = ("garage_pass", "monthly_billing", "psycopg", "psycopg2", "asyncpg",
                      "sqlite3", "sqlalchemy")


def _modules() -> dict[str, ast.AST]:
    return {p.name: ast.parse(p.read_text()) for p in sorted(SRC.glob("*.py"))}


def imported_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def environment_reads(tree: ast.AST) -> list[str]:
    """Every `os.environ[...]`, `os.environ.get(...)`, `os.getenv(...)`,
    `environ[...]` in one module, as source text."""
    found: list[str] = []
    for node in ast.walk(tree):
        text = ast.unparse(node)
        if isinstance(node, ast.Attribute) and node.attr in ("environ", "environb", "getenv"):
            found.append(text)
        elif isinstance(node, ast.Name) and node.id in ("environ", "getenv"):
            found.append(text)
    return found


def forbidden_imports() -> dict[str, set[str]]:
    return {
        name: imported_names(tree) & set(FORBIDDEN_PACKAGES)
        for name, tree in _modules().items()
        if imported_names(tree) & set(FORBIDDEN_PACKAGES)
    }


def all_environment_reads() -> dict[str, list[str]]:
    return {name: reads for name, tree in _modules().items() if (reads := environment_reads(tree))}


def migration_directories(root: Path = ROOT) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("migrations")
                  if p.is_dir() and ".pins" not in p.parts and ".git" not in p.parts)


def runtime_dependencies() -> list[str]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"]


@pytest.mark.guarantee("C3")
def test_the_scan_is_pointed_at_the_real_package():
    modules = _modules()
    assert {"cli.py", "doors.py", "sync.py", "live.py", "links.py"} <= set(modules)
    assert "subprocess" in imported_names(modules["doors.py"]), "doors.py runs no subprocess"


@pytest.mark.guarantee("C3")
def test_the_package_imports_neither_module_and_no_driver():
    assert forbidden_imports() == {}, forbidden_imports()


@pytest.mark.guarantee("C3")
def test_the_package_reads_no_environment_variable():
    assert all_environment_reads() == {}, all_environment_reads()


@pytest.mark.guarantee("C3")
def test_there_is_no_migrations_directory():
    assert migration_directories() == []


@pytest.mark.guarantee("C3")
def test_a_planted_migrations_directory_is_REFUSED():
    """The directory plant, in a `finally`: the checker must see it."""
    planted = ROOT / "migrations"
    assert not planted.exists(), "the plant path is already occupied"
    try:
        planted.mkdir()
        (planted / "0001_planted.sql").write_text("-- PLANTED\n")
        assert migration_directories() == ["migrations"]
    finally:
        shutil.rmtree(planted, ignore_errors=True)
    assert not planted.exists()


@pytest.mark.guarantee("C3")
def test_the_runtime_dependency_list_is_empty():
    assert runtime_dependencies() == []
    requires = metadata.distribution("openparking-pass-billing-connector").requires or []
    assert [r for r in requires if "extra ==" not in r] == []


@pytest.mark.guarantee("C3")
def test_the_installed_modules_are_the_pinned_commits():
    pins = pinned_commits()
    for module, sha in pins.items():
        distribution = metadata.distribution(f"openparking-{module}")
        direct = distribution.read_text("direct_url.json")
        assert direct, f"openparking-{module} was not installed from a URL"
        info = json.loads(direct)
        assert info.get("vcs_info", {}).get("commit_id") == sha, (module, info)


@pytest.mark.guarantee("C3")
def test_a_missing_console_script_is_refused_by_name_before_any_link(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))  # nothing on it
    links = tmp_path / "links.json"
    links.write_text('{"links": []}')
    with pytest.raises(doors.ScriptMissing):
        doors.require_scripts()
    code = cli.main(["sync", "--links", str(links), "--at", "2026-09-16T09:00:00-06:00"])
    assert code == 2


@pytest.mark.guarantee("C3")
def test_the_scripts_are_the_two_published_ones():
    assert doors.SCRIPTS == ("garage-pass", "monthly-billing")
