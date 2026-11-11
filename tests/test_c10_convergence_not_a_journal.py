"""C10 -- convergence, not a journal.

§5.7: a run killed between the registers and the releases, then re-run --
converged. The kill is a release door that raises `KeyboardInterrupt` the
first time it is asked (the shape of an operator's Ctrl-C mid-run), against
the REAL modules: the registers it made before the kill are in billing, the
releases are not, and the next run repairs it from fresh reads because the
connector kept nothing from the first.

And the package keeps nothing: no file is opened for writing anywhere in
the runtime source, read from the AST.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from harness import AT, needs_databases, standard_world
from pass_billing_connector import doors
from pass_billing_connector import sync as sync_module

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "pass_billing_connector"


def writes_in(tree: ast.AST) -> list[str]:
    """Every `open(..., 'w'...)`, `.write_text(`, `.write_bytes(`, `.mkdir(`
    in one module, as source text."""
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        text = ast.unparse(node)
        func = node.func
        if isinstance(func, ast.Name) and func.id == "open":
            modes = list(node.args[1:2])
            modes += [k.value for k in node.keywords if k.arg == "mode"]
            if any(isinstance(m, ast.Constant) and any(c in m.value for c in "wax+")
                   for m in modes):
                found.append(text)
        elif isinstance(func, ast.Attribute) and func.attr in ("write_text", "write_bytes",
                                                                "mkdir", "makedirs"):
            found.append(text)
    return found


def all_writes() -> dict[str, list[str]]:
    return {p.name: w for p in sorted(SRC.glob("*.py"))
            if (w := writes_in(ast.parse(p.read_text())))}


@pytest.mark.guarantee("C10")
def test_the_package_writes_no_file():
    assert all_writes() == {}, all_writes()


@pytest.mark.guarantee("C10")
def test_the_write_scan_finds_a_planted_write(tmp_path):
    planted = tmp_path / "p.py"
    planted.write_text("from pathlib import Path\nPath('state.json').write_text('x')\n"
                       "open('journal', 'a').write('y')\n")
    assert len(writes_in(ast.parse(planted.read_text()))) == 2


# ------------------------------------------------------------ the database


@needs_databases
@pytest.mark.guarantee("C10")
def test_a_run_killed_between_the_registers_and_the_releases_is_repaired_by_the_next(
    pair, monkeypatch,
):
    standard_world(pair)
    pair.mb_register("ag-1", "Stale 1")
    pair.gp_register("pass-1", "garage-a", "AB-123", "2026-09-01")

    real_release = doors.release_vehicle
    killed = {"count": 0}

    def release_then_die(*args, **kwargs):
        killed["count"] += 1
        raise KeyboardInterrupt("the operator's Ctrl-C, mid-run")

    monkeypatch.setattr(sync_module.doors, "release_vehicle", release_then_die)
    with pytest.raises(KeyboardInterrupt):
        pair.sync([pair.link()], AT, monkeypatch=monkeypatch)
    assert killed["count"] == 1
    # Half-way: the register landed, the release did not.
    assert pair.mb_rows("ag-1") == {("garage-a", "ab123"), ("garage-b", "AB-123"),
                                    ("garage-a", "stale1"), ("garage-b", "Stale 1")}

    monkeypatch.setattr(sync_module.doors, "release_vehicle", real_release)
    code, report = pair.sync([pair.link()], AT, monkeypatch=monkeypatch)
    assert code == 0, report
    assert pair.mb_rows("ag-1") == {("garage-a", "ab123"), ("garage-b", "AB-123")}


@needs_databases
@pytest.mark.guarantee("C10")
def test_a_link_billing_already_holds_correctly_makes_no_write(pair, monkeypatch):
    """Recorded, not assumed: with the register already equal, the only door
    calls a run makes are reads and the idempotent registers -- no release."""
    standard_world(pair)
    pair.gp_register("pass-1", "garage-a", "AB-123", "2026-09-01")
    assert pair.sync([pair.link()], AT, monkeypatch=monkeypatch)[0] == 0
    calls: list[str] = []
    real_run = doors._run

    def recording_run(argv):
        calls.append(argv[1])
        return real_run(argv)

    monkeypatch.setattr(doors, "_run", recording_run)
    code, report = pair.sync([pair.link()], AT, monkeypatch=monkeypatch)
    assert code == 0
    assert "release-vehicle" not in calls
    assert calls.count("register-vehicle") == 1
    assert calls.count("show-pass") == 2 and calls.count("show-register") == 3
