"""C15 -- the exit guarantee.

The connector touches registrations only. Its subprocess calls are exactly
five verbs, three reads and two registration writes -- read from `doors.py`'s
source; its own command line has one
verb, `sync`; no key of its report could deny an exit; and garage-pass's own
access answer at a lane is the same before and after a run. Nothing here can
trap a car in a garage.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from harness import AT, needs_databases, standard_world
from pass_billing_connector import cli
from pass_billing_connector.report import report_keys

ROOT = Path(__file__).resolve().parent.parent
DOORS = ROOT / "src" / "pass_billing_connector" / "doors.py"

PUBLISHED_VERBS = {"show-pass", "show-garage-register", "show-register", "register-vehicle",
                   "release-vehicle"}


def subprocess_verbs() -> set[str]:
    """The second element of every argv list handed to `_run` in doors.py."""
    verbs: set[str] = set()
    for node in ast.walk(ast.parse(DOORS.read_text())):
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "_run":
            (argv,) = node.args
            assert isinstance(argv, ast.List), ast.unparse(node)
            verb = argv.elts[1]
            assert isinstance(verb, ast.Constant), ast.unparse(node)
            verbs.add(verb.value)
    return verbs


@pytest.mark.guarantee("C15")
def test_the_subprocess_verbs_are_exactly_the_registration_and_read_verbs():
    assert subprocess_verbs() == PUBLISHED_VERBS


@pytest.mark.guarantee("C15")
def test_the_connector_has_no_exit_verb_and_no_exit_key():
    assert cli.VERBS == ("sync",)
    published = {k for keys in report_keys().values() for k in keys}
    assert not any("exit" in k or "deny" in k or "denied" in k for k in published), published
    # `refused` is there: it says the LINK was refused before any write. It is
    # a fact about a reconciliation run, and nothing at a lane reads it.
    assert "refused" in published


# ------------------------------------------------------------ the database


@needs_databases
@pytest.mark.guarantee("C15")
def test_garage_pass_access_answer_is_the_same_before_and_after_a_run(pair, monkeypatch):
    standard_world(pair)
    pair.gp_register("pass-1", "garage-a", "AB-123", "2026-09-01")
    pair.mb_register("ag-1", "Stale 1")  # something for the run to release

    def access(direction: str) -> dict:
        done = pair.gp_run("access-in-store", "--garage", "garage-a", "--vehicle", "AB-123",
                           "--lane", "L1", "--direction", direction, "--at", AT, check=False)
        return {"exit": done.returncode, "answer": json.loads(done.stdout)}

    before = {d: access(d) for d in ("entry", "exit")}
    code, _ = pair.sync([pair.link()], AT, monkeypatch=monkeypatch)
    assert code == 0
    after = {d: access(d) for d in ("entry", "exit")}
    assert after == before
    assert before["entry"]["exit"] == 0, before  # the car is covered at the lane
    assert before["exit"]["exit"] == 0, before   # and an exit is never refused
