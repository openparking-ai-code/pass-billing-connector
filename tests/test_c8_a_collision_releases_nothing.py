"""C8 -- a collision releases nothing.

§5.4: two live plates on the pass, `AB-123` and `ab123`, fold to ONE stored
form at garage-a. Releasing either would take out the other, so the link is
reported (garage, form, both identities), nothing is released for it -- a
foreign row that would otherwise go stays -- it does not converge, exit 1.
"""

from __future__ import annotations

import pytest

from harness import AT, needs_databases, standard_world


@needs_databases
@pytest.mark.guarantee("C8")
def test_two_live_plates_one_form_is_a_collision_and_nothing_is_released(pair, monkeypatch):
    standard_world(pair)
    pair.mb_register("ag-1", "Foreign 9")  # would be released on a healthy link
    pair.gp_register("pass-1", "garage-a", "AB-123", "2026-09-01")
    pair.gp_register("pass-1", "garage-a", "ab123", "2026-09-01")
    code, report = pair.sync([pair.link()], AT, monkeypatch=monkeypatch)
    assert code == 1
    (one,) = report["links"]
    assert one["converged"] is False and one["refused"] is False
    assert all(a["action"] == "register" for a in one["actions"]), one["actions"]
    collisions = [f for f in one["findings"] if f["code"] == "COLLISION"]
    assert len(collisions) == 1
    (collision,) = collisions
    assert collision["garage"] == "garage-a" and collision["form"] == "ab123"
    assert collision["identities"] == ["AB-123", "ab123"]
    # Nothing released: the foreign row is still there, and so are both cars.
    assert pair.mb_rows("ag-1") == {("garage-a", "ab123"), ("garage-b", "AB-123"),
                                    ("garage-b", "ab123"), ("garage-a", "foreign9"),
                                    ("garage-b", "Foreign 9")}


@needs_databases
@pytest.mark.guarantee("C8")
def test_the_same_two_plates_at_the_exact_garage_alone_are_not_a_collision(pair, monkeypatch):
    """The control on the fixture axis: the collision is the FOLDED rule's.
    A pass over garage-b alone (exact) holds both plates as two rows."""
    for garage_id, zone in (("garage-a", "America/Denver"), ("garage-b", "Europe/Berlin")):
        pair.gp_garage(garage_id, zone)
    pair.gp_pass("pass-1", ("garage-b",), valid_from="2026-01-01", valid_to="2026-12-31")
    from harness import GARAGE_A, GARAGE_B, mb_agreement, mb_garage

    pair.mb_seed(tuple(mb_garage(g, z, r) for g, z, r in (GARAGE_A, GARAGE_B)),
                 (mb_agreement("ag-1", "garage-b", ("garage-b",)),))
    pair.gp_register("pass-1", "garage-b", "AB-123", "2026-09-01")
    pair.gp_register("pass-1", "garage-b", "ab123", "2026-09-01")
    code, report = pair.sync([pair.link(pass_garage="garage-b")], AT, monkeypatch=monkeypatch)
    assert code == 0, report
    assert pair.mb_rows("ag-1") == {("garage-b", "AB-123"), ("garage-b", "ab123")}
