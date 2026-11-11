"""C1 -- no test module sits outside the guarantee registry.

**THE HOLE THIS CLOSES.** `conftest.py` fails a run when a REGISTERED GUARANTEE
did not run and pass. That is a set comparison over guarantee ids, so it is blind
to a test module that registers nothing at all: skip it, delete it, or let it
stop collecting, and every gate stays green because no id went missing.

In monthly-billing, where this guard was written, two modules were in exactly
that position -- 16 tests carrying the anti-prose controls and the controls on
the fixtures its DST guarantee was measured with -- and a review skipped one at
module level while the suite reported 124 passed, exit 0. A sibling repository
shipped the same shape: 21 tests outside both guards.

Copied here before the first module test exists, so the hole is closed on the
day the first test module lands. **It is DERIVED**: the module set comes off
the filesystem and the marks come out of the AST, so a file that arrives next
round cannot arrive unnoticed.

**READ WITH THE AST, NEVER WITH A REGEX.** This file writes
`@pytest.mark.guarantee(...)` inside the string literal it plants below. A text
scan would count that as a mark on THIS module and report it guarded whatever its
real decorators said -- a check measuring the word instead of the shape, which is
the failure this project keeps cataloguing.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from _guarantees import GUARANTEES

ROOT = Path(__file__).resolve().parent.parent

#: Modules deliberately contributing no guarantee. EMPTY, and an entry here is a
#: decision somebody writes down -- the same shape as ALLOW_ENV, for the same
#: reason. A module that PLANTS may not be listed: see the second rule below.
UNGUARANTEED_MODULES: frozenset[str] = frozenset()


def _declared_guarantee_ids(tree: ast.AST) -> set[str]:
    """The ids on real `@pytest.mark.guarantee(...)` DECORATORS in one module."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            call = decorator if isinstance(decorator, ast.Call) else None
            if call is None or not isinstance(call.func, ast.Attribute):
                continue
            if call.func.attr != "guarantee":
                continue
            found |= {
                arg.value
                for arg in call.args
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
            }
    return found


def _imports_the_plant_helper(tree: ast.AST) -> bool:
    """Does this module import `planted` -- i.e. does it break source on purpose?"""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "plant":
            if any(alias.name == "planted" for alias in node.names):
                return True
    return False


def _test_modules() -> dict[str, ast.AST]:
    """Derived from the filesystem, so a new file is in the set the day it lands."""
    return {
        path.name: ast.parse(path.read_text())
        for path in sorted((ROOT / "tests").glob("test_*.py"))
    }


def unguarded_modules() -> dict[str, str]:
    """Every test module no registered guarantee names, and why that is wrong.

    1. A test module contributes at least one registered guarantee, or is named
       in UNGUARANTEED_MODULES.
    2. **A module that PLANTS a defect must contribute one, with no allowance.**
       Going to the trouble of breaking source on purpose means producing
       evidence, and evidence nothing names is evidence nothing protects.
    """
    problems: dict[str, str] = {}
    for name, tree in _test_modules().items():
        ids = _declared_guarantee_ids(tree)
        unknown = sorted(ids - set(GUARANTEES))
        if unknown:
            problems[name] = f"claims unregistered guarantee id(s): {', '.join(unknown)}"
        elif ids:
            continue
        elif _imports_the_plant_helper(tree):
            problems[name] = (
                "plants a defect but registers no guarantee, and a planting module "
                "may not be excused -- delete it and the suite stays green while a "
                "control silently stops existing"
            )
        elif name not in UNGUARANTEED_MODULES:
            problems[name] = (
                "carries no @pytest.mark.guarantee, so deleting or skipping it leaves "
                "the suite green and this guard silent"
            )
    return problems


@pytest.mark.guarantee("C1")
def test_the_module_scan_is_pointed_at_a_real_set():
    """The control on the denominator. An empty scan reports every module guarded."""
    modules = _test_modules()
    assert len(modules) >= 2, f"the scan found only {len(modules)} test modules"
    assert "test_contract_is_generated.py" in modules
    assert Path(__file__).name in modules, "this module is outside its own scan"


@pytest.mark.guarantee("C1")
def test_every_test_module_contributes_a_registered_guarantee():
    problems = unguarded_modules()
    assert not problems, "test modules outside both guards:\n  " + "\n  ".join(
        f"{name}: {why}" for name, why in sorted(problems.items())
    )


@pytest.mark.guarantee("C1")
def test_a_module_that_registers_nothing_is_REFUSED():
    """THE FAIL-CONTROL, and it plants a real file in the real `tests/` tree.

    Not a temp directory: the guard reads `tests/` off the filesystem, so a
    control pointed at a copy would prove the derivation works somewhere the
    derivation never runs. Restored in a `finally`, from the bytes written --
    never `git checkout`.
    """
    intruder = ROOT / "tests" / "test_zz_planted_intruder.py"
    assert not intruder.exists(), "the intruder path is already occupied"
    body = (
        '"""A module with no mark at all, which is what this control is."""\n\n\n'
        "def test_it_registers_no_guarantee():\n"
        "    assert True\n"
    )
    try:
        intruder.write_text(body)
        problems = unguarded_modules()
        assert intruder.name in problems, (
            "a module registering no guarantee was accepted, so the hole that hid "
            "16 tests here and 21 in a sibling repository is still open"
        )
        assert "no @pytest.mark.guarantee" in problems[intruder.name]
    finally:
        intruder.unlink(missing_ok=True)
    assert not intruder.exists(), "the planted intruder was not removed"


@pytest.mark.guarantee("C1")
def test_a_module_LEGITIMATELY_outside_the_set_is_not_flagged():
    """The other arm, without which this guard is a rule nobody can satisfy.

    A guard that flags every module whatever the allowance says is not deriving
    anything -- it is refusing unconditionally, and the first person to meet it
    widens it until it stops working. So: a non-planting module named in
    UNGUARANTEED_MODULES is accepted, and the SAME module is flagged the moment
    the allowance is taken away.
    """
    intruder = ROOT / "tests" / "test_zz_planted_allowed.py"
    assert not intruder.exists(), "the intruder path is already occupied"
    body = (
        '"""A module with no mark, named in the allowance."""\n\n\n'
        "def test_it_registers_no_guarantee():\n"
        "    assert True\n"
    )
    try:
        intruder.write_text(body)
        assert intruder.name in unguarded_modules(), (
            "the control is degenerate: this module is not flagged even unallowed"
        )

        import test_guarantee_guard as self_module

        original = self_module.UNGUARANTEED_MODULES
        try:
            self_module.UNGUARANTEED_MODULES = frozenset({intruder.name})
            assert intruder.name not in unguarded_modules(), (
                "a non-planting module named in UNGUARANTEED_MODULES was still "
                "flagged, so the allowance does not work and the guard is a rule "
                "nobody can satisfy"
            )
        finally:
            self_module.UNGUARANTEED_MODULES = original
    finally:
        intruder.unlink(missing_ok=True)
    assert not intruder.exists(), "the planted intruder was not removed"


@pytest.mark.guarantee("C1")
def test_a_module_that_PLANTS_and_registers_nothing_cannot_be_excused():
    """Rule 2 has no escape hatch, and the allowance may not buy one out."""
    intruder = ROOT / "tests" / "test_zz_planted_planter.py"
    assert not intruder.exists(), "the intruder path is already occupied"
    body = (
        "from plant import planted\n\n\n"
        "def test_it_plants_but_names_no_guarantee():\n"
        "    with planted('cli.py', 'def main', 'def main'):\n"
        "        pass\n"
    )
    try:
        intruder.write_text(body)
        assert "may not be excused" in unguarded_modules()[intruder.name]

        import test_guarantee_guard as self_module

        original = self_module.UNGUARANTEED_MODULES
        try:
            self_module.UNGUARANTEED_MODULES = frozenset({intruder.name})
            assert intruder.name in unguarded_modules(), (
                "naming a PLANTING module in UNGUARANTEED_MODULES excused it; the "
                "allowance must not reach rule 2"
            )
        finally:
            self_module.UNGUARANTEED_MODULES = original
    finally:
        intruder.unlink(missing_ok=True)
    assert not intruder.exists(), "the planted intruder was not removed"


@pytest.mark.guarantee("C1")
def test_a_mark_naming_an_unregistered_id_is_REFUSED():
    """The reverse direction: a module claiming a guarantee nobody registered.

    `conftest.py` catches this at collection for ids it can see; this catches it
    from the AST, so it holds for a module that never collects.
    """
    intruder = ROOT / "tests" / "test_zz_planted_unknown_id.py"
    assert not intruder.exists(), "the intruder path is already occupied"
    body = (
        "import pytest\n\n\n"
        '@pytest.mark.guarantee("NOT_IN_THE_REGISTRY")\n'
        "def test_it_claims_an_id_nobody_registered():\n"
        "    assert True\n"
    )
    try:
        intruder.write_text(body)
        assert "NOT_IN_THE_REGISTRY" in unguarded_modules()[intruder.name]
    finally:
        intruder.unlink(missing_ok=True)
    assert not intruder.exists(), "the planted intruder was not removed"
