"""Planting a defect in the source, and putting it back.

Every guarantee is proven able to fail by breaking the thing it guards and
watching it go red. The restore writes back the exact bytes that were there, in a
`finally`, and verifies them -- **never `git checkout`**, which has been broken
twice on this project and would take a co-resident session's uncommitted work
with it.

**The plant runs the test in a SUBPROCESS, and this is the second design.** The
first reloaded the planted module in-process with `importlib.reload`, and it was
quietly broken in a way worth recording here, because it is the shape of defect
this project keeps finding: a reload REBINDS a module's exception classes, so the
`NotMinorUnits` a reloaded module raises is a different class object from the
`NotMinorUnits` the test file imported at collection time. `pytest.raises` then
does not catch it, the control fails for a reason unrelated to the defect it
planted, and -- the part that matters -- a control written slightly differently
would instead have PASSED for a reason unrelated to the defect. A fresh
interpreter has no identity problem to get wrong.

Two guards on the plant itself:

* **The anchor must appear EXACTLY ONCE.** Zero matches plants nothing and the
  control then reports red from unmodified source. Two matches lands in the wrong
  place. Both are checked before a byte is written.
* **The restore is verified, not assumed.** A restore that silently failed leaves
  a planted defect in the working tree for everything that runs after it.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "pass_billing_connector"

#: Path prefixes that are resolved against ROOT rather than against SRC.
#:
#: Inherited from monthly-billing, where every plant used to land in the engine
#: until the guard on the guarantees needed a control of its own: `tests/conftest.py`
#: is the thing that fails a run when a registered guarantee stops running, and
#: no plant in the package can reach it. Here `pyproject.toml` is on the list
#: too: the "no database" guarantee is partly a claim about the dependency list,
#: and its control plants a driver there.
#:
#: Explicit prefixes rather than "does it contain a slash", so anything cleverer
#: cannot silently retarget a control that already exists.
ROOT_RELATIVE_PREFIXES: tuple[str, ...] = ("tests/", "scripts/", "docs/", "pyproject.toml")


def resolve(relative_path: str) -> Path:
    """Where a plant's path points. ONE resolver, used by the plant and by the
    anchor pre-flight -- two copies would let `--anchors` report a live anchor in
    a file the plant then never writes to."""
    base = ROOT if relative_path.startswith(ROOT_RELATIVE_PREFIXES) else SRC
    path = (base / relative_path).resolve()
    if not path.is_relative_to(ROOT):
        raise AssertionError(
            f"a plant resolved to {path}, which is outside the repository. A control "
            "that writes outside the tree is not a control, it is an accident."
        )
    return path


@contextmanager
def planted(relative_path: str, frm: str, to: str):
    path = resolve(relative_path)
    original = path.read_text()

    occurrences = original.count(frm)
    if occurrences != 1:
        raise AssertionError(
            f"the anchor for this fail-control appears {occurrences} times in "
            f"{relative_path}, not once. A plant that cannot find its anchor proves "
            "nothing; one that finds two lands in the wrong place. Fix the anchor "
            "before trusting anything this control reports."
        )

    try:
        _write(path, original.replace(frm, to))
        yield
    finally:
        _write(path, original)
        if path.read_text() != original:
            raise AssertionError(
                f"{relative_path} was NOT restored -- a planted defect is still in "
                "the working tree. Restore it by hand before running anything else."
            )


#: Every write through this helper gets a distinct modification time. See _write.
_writes = 0


def _write(path: Path, text: str) -> None:
    """Write, and make sure Python cannot serve the PREVIOUS bytecode for it.

    CPython validates a cached `.pyc` against the source's (mtime IN WHOLE
    SECONDS, size). A plant that changes a file without changing its SIZE, inside
    the same second as the last write, is therefore invisible to any subprocess:
    it imports the stale bytecode, behaves exactly as if nothing was planted, and
    the control reports GREEN against a defect that was never actually loaded.

    **THIS IS NOT HYPOTHETICAL, AND IT IS NOT THIS REPOSITORY'S OWN LESSON.** A
    sibling module in this project hit it: a control that moved one line from one
    registry into another produced a file byte-for-byte the same LENGTH, and the
    rendered document came back unplanted. The failure mode is the worst kind
    this project catalogues -- a check shaped like evidence that cannot produce a
    negative result, and one that would have looked like a REAL finding rather
    than like a broken test.

    It is inherited here deliberately rather than rediscovered. None of this
    module's controls happens to be size-preserving today, and that is luck: the
    next plant somebody writes should not have to depend on it. So the mtime is
    advanced past any cached entry on every write.

    **AND THE CACHED BYTECODE IS DELETED, because advancing the mtime was not
    enough on its own.** Measured, not reasoned about: with only the mtime
    advance, `test_a_size_preserving_plant_is_actually_loaded` failed on 3 runs
    in 6 and twice took the whole module red BEFORE anything was planted, which
    `fail_controls.py` correctly reported as UNMEASURED -- a control set that
    intermittently cannot say whether it ran. The mtime this helper writes is
    `now + n`, i.e. in the FUTURE, so a `.pyc` left behind by an earlier run can
    record a stamp that a later run's plant collides with in whole seconds; the
    size is identical by construction in exactly the plants this guards, and the
    two together are precisely CPython's cache key.

    Removing the cache entry closes the class rather than the instance. There is
    no arithmetic left to get wrong: bytecode that does not exist cannot be
    served stale.
    """
    global _writes
    _writes += 1
    path.write_text(text)
    stamp = time.time() + _writes
    os.utime(path, (stamp, stamp))

    cached = Path(importlib.util.cache_from_source(str(path)))
    cached.unlink(missing_ok=True)


def run_tests(target: str) -> subprocess.CompletedProcess:
    """Run one test target in a fresh interpreter and return the result."""
    return subprocess.run(
        [sys.executable, "-m", "pytest", target, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
