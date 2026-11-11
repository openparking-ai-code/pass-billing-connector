"""C16 -- every fixture carries its own control.

The linked fixture's two garages DIFFER in billing identity rule: garage-a
folds, garage-b is exact. Every test that measures "releases by stored form"
or "a swap whose plates fold to one form" samples the axis that decides only
if that is true, so it is asserted here as a test rather than trusted from
a comment -- against billing's own rule, at the pinned commit.
"""

from __future__ import annotations

import pytest

from harness import GARAGE_A, GARAGE_B, mb_garage

#: The swap plates every fold-to-one-form test uses.
OLD, NEW = "ab123", "AB-123"


@pytest.mark.guarantee("C16")
def test_the_two_garages_differ_in_identity_rule():
    assert GARAGE_A[2] != GARAGE_B[2], (GARAGE_A, GARAGE_B)
    assert {GARAGE_A[2], GARAGE_B[2]} == {"folded_alphanumeric", "exact"}


@pytest.mark.guarantee("C16")
def test_the_swap_plates_fold_to_one_form_under_folded_and_two_under_exact():
    """Measured with the module's own rule, not restated."""
    from monthly_billing.cli import load_garage_file

    from harness import _tmp_json

    folded = load_garage_file(_tmp_json(mb_garage(*GARAGE_A)))
    exact = load_garage_file(_tmp_json(mb_garage(*GARAGE_B)))
    assert folded.normalise_identity(OLD) == folded.normalise_identity(NEW)
    assert exact.normalise_identity(OLD) != exact.normalise_identity(NEW)


@pytest.mark.guarantee("C16")
def test_the_two_garages_are_in_different_zones():
    """The day-as-written guarantee is only exercised across zones if the
    fixture garages sit in different ones."""
    assert GARAGE_A[1] != GARAGE_B[1]
