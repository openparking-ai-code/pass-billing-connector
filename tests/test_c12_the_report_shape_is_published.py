"""C12 -- the report's shape is published and generated.

The keys come off the dataclasses; every finding code, side, action, outcome
and reason the source EMITS is in the registry the contract is generated
from -- read from the AST of `sync.py` and `doors.py`, so a code typed into
a `Finding(...)` or an `Action(...)` that nobody published is found here
before it reaches a report; and every key in a rendered report is one the
contract lists.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from pass_billing_connector import findings as registry
from pass_billing_connector.report import Action, Finding, LinkReport, Report, Row, report_keys

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "pass_billing_connector"

#: Every registered code, by the constant that names it.
CODES: dict[str, str] = {
    name: value for name, value in vars(registry).items()
    if name.startswith(("FINDING_", "SIDE_", "ACTION_", "OUTCOME_", "REASON_"))
    and isinstance(value, str)
}
REGISTERED: set[str] = (set(registry.FINDINGS) | set(registry.SIDES) | set(registry.ACTIONS)
                        | set(registry.OUTCOMES) | set(registry.REASONS))


def emitted_codes() -> dict[str, list[str]]:
    """Every value handed to a Finding/Action/Read/Answer as a code, side,
    action, outcome or reason, per module: a constant's name (resolved) or a
    bare string literal -- the two ways a code is typed."""
    out: dict[str, list[str]] = {}
    keyword_fields = {"code", "side", "action", "outcome", "reason", "finding"}
    for path in sorted(SRC.glob("*.py")):
        tree = ast.parse(path.read_text())
        found: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            callee = ast.unparse(node.func).split(".")[-1]
            if callee not in ("Finding", "Action", "Read", "Answer"):
                continue
            positional = node.args[:1] if callee in ("Finding", "Answer") else []
            if callee == "Read":
                positional = node.args[1:2]
            values = list(positional) + [k.value for k in node.keywords if k.arg in keyword_fields]
            for value in values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    found.append(value.value)
                elif isinstance(value, ast.Name) and value.id in CODES:
                    found.append(CODES[value.id])
                elif isinstance(value, ast.Attribute) and value.attr in CODES:
                    found.append(CODES[value.attr])
                # A variable or an expression (`reason`, `answer.outcome`,
                # `pass_read.finding`) carries a value that was itself made
                # from a constant or a literal, and was checked where it was.
        if found:
            out[path.name] = found
    return out


@pytest.mark.guarantee("C12")
def test_every_registered_constant_is_in_a_registry_table():
    unlisted = sorted(v for v in CODES.values() if v not in REGISTERED)
    assert unlisted == [], unlisted


@pytest.mark.guarantee("C12")
def test_every_emitted_code_is_registered():
    emitted = emitted_codes()
    assert emitted, "the scan found no emission at all"
    unregistered = {
        name: sorted(v for v in values if v not in REGISTERED)
        for name, values in emitted.items()
        if any(v not in REGISTERED for v in values)
    }
    assert unregistered == {}, unregistered


@pytest.mark.guarantee("C12")
def test_the_scan_sees_a_planted_unregistered_code(tmp_path, monkeypatch):
    planted = tmp_path / "planted.py"
    planted.write_text('from x import Finding\nFinding("NOBODY_PUBLISHED_THIS", "d")\n')
    monkeypatch.setattr("test_c12_the_report_shape_is_published.SRC", tmp_path)
    assert emitted_codes() == {"planted.py": ["NOBODY_PUBLISHED_THIS"]}


@pytest.mark.guarantee("C12")
def test_the_report_keys_are_derived_from_the_dataclasses():
    keys = report_keys()
    assert set(keys) == {"Report", "LinkReport", "Action", "Finding", "Row"}
    assert keys["Report"] == ("at", "day", "converged", "links")
    assert keys["Row"] == ("garage", "form")


@pytest.mark.guarantee("C12")
def test_a_rendered_report_carries_only_published_keys():
    report = Report(
        at="2026-09-16T09:00:00-06:00", day="2026-09-16", converged=False,
        links=(LinkReport(
            pass_tenant="t", pass_id="p", pass_garage="g", billing_tenant="b", agreement_id="a",
            converged=False, refused=False, live={"g": ("X",)},
            expected=(Row("g", "x"),), billing=(),
            actions=(Action("register", "done", "live on the day", identity="X",
                            stored={"g": "x"}),),
            findings=(Finding("DIVERGENCE", "d", garage="g", form="x", side="pass_only"),),
        ),),
    )
    document = report.as_document()
    published = report_keys()
    assert set(document) == set(published["Report"])
    (link,) = document["links"]
    assert set(link) == set(published["LinkReport"])
    assert set(link["actions"][0]) == set(published["Action"])
    assert set(link["findings"][0]) == set(published["Finding"])
    assert set(link["expected"][0]) == set(published["Row"])
    # Every key present on every instance: a field that does not apply is null.
    assert link["actions"][0]["form"] is None and link["findings"][0]["identity"] is None


@pytest.mark.guarantee("C12")
def test_the_exit_codes_are_published():
    assert set(registry.EXITS) == {0, 1, 2}
