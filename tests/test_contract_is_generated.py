"""C2 -- docs/CONTRACT.md is generated, and generation is not verification.

`scripts/generate_contract.py --check` proves the document matches its
generator. It cannot prove the generator DERIVES anything: a template whose
prose is fixed everywhere except the holes agrees with itself perfectly. So
each test here plants a value that contradicts a published sentence and
requires the rendered sentence to CHANGE. A sentence that survives its plant
is a fixed string, and this file is where that would be found out.

Every plant runs the generator in a fresh interpreter (`plant.run` below), so
the module-level registries it imports are re-read from the planted files
rather than served from this process's cache.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from plant import planted

ROOT = Path(__file__).resolve().parent.parent
GENERATOR = ROOT / "scripts" / "generate_contract.py"
DOC = ROOT / "docs" / "CONTRACT.md"


def rendered() -> str:
    """The document as the generator would write it now, without writing it."""
    code = (
        "import sys; sys.argv = ['generate_contract.py']\n"
        f"sys.path.insert(0, {str(GENERATOR.parent)!r})\n"
        "import generate_contract as g\n"
        "sys.stdout.write(g.render(g.DOC.read_text()))\n"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          cwd=ROOT, check=True)
    return done.stdout


def check() -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(GENERATOR), "--check"], capture_output=True,
                          text=True, cwd=ROOT)


@pytest.mark.guarantee("C2")
def test_the_document_is_the_generated_one():
    done = check()
    assert done.returncode == 0, done.stdout + done.stderr


@pytest.mark.guarantee("C2")
def test_a_guarantee_sentence_moved_in_the_registry_moves_the_document():
    before = rendered()
    with planted(
        "tests/_guarantees.py",
        '"C1": (\n        "Every test module contributes',
        '"C1": (\n        "PLANTED: every test module contributes',
    ):
        after = rendered()
        assert check().returncode == 1, "--check stayed green under a planted registry"
    assert "PLANTED: every test module" in after
    assert "PLANTED" not in before
    assert rendered() == before, "the plant was not restored"


@pytest.mark.guarantee("C2")
def test_the_guarantee_count_is_derived_not_typed():
    before = rendered()
    assert "That is 2 guarantees" in before or "That is " in before
    with planted(
        "tests/_guarantees.py",
        '    "C2": (',
        '    "C99": ("PLANTED: a guarantee that exists only to move the count."),\n    "C2": (',
    ):
        after = rendered()
    count_before = before.split("That is ")[-1].split(" guarantees")[0]
    count_after = after.split("That is ")[-1].split(" guarantees")[0]
    assert int(count_after) == int(count_before) + 1, (count_before, count_after)


@pytest.mark.guarantee("C2")
def test_a_pin_moved_in_pyproject_moves_the_document():
    before = rendered()
    with planted(
        "pyproject.toml",
        "garage-pass@253249b5eb52770ec14d026f04f2c39749b75530",
        "garage-pass@0000000000000000000000000000000000000000",
    ):
        after = rendered()
    assert "0000000000000000000000000000000000000000" in after
    assert "253249b5eb52770ec14d026f04f2c39749b75530" in before


@pytest.mark.guarantee("C2")
def test_check_writes_nothing_even_when_it_fails():
    before = hashlib.sha256(DOC.read_bytes()).hexdigest()
    with planted("tests/_guarantees.py", '"C2": (', '"C2": (\n        "PLANTED "'):
        assert check().returncode == 1
    assert hashlib.sha256(DOC.read_bytes()).hexdigest() == before
