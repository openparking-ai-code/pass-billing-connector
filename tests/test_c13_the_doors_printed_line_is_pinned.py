"""C13 -- the door's printed line is pinned.

`  at garage {garage}: {form}` is the one piece of prose the connector reads.
It is matched against garage ids the register read already named, so the
form after the garage may contain anything -- `: ` included -- and a line
naming no known garage makes the whole answer unparseable rather than
half-read.

THE ONE SHAPE NO PARSER CAN READ. With covered ids `g` and `g: 2`, the line
`  at garage g: 2: x1` is garage `g` storing `2: x1` AND garage `g: 2`
storing `x1`, byte for byte. The parser's longest-first order picks one, and
for a release that printed one such line the pick is a guess. So a covered
set in which one id is another id plus the separator plus anything is
refused before any write (`GARAGE_IDS_AMBIGUOUS`, the pure half here and
the real world in `test_c11_...`), and the parser is never asked.

The database half runs the real door at the pinned commit and asserts the
exact lines, so a change there reddens this repository before it mis-parses.
"""

from __future__ import annotations

from datetime import date

import pytest

from harness import AT, needs_databases, standard_world
from pass_billing_connector import doors
from pass_billing_connector import sync as sync_module
from pass_billing_connector.doors import STORED_FORM_LINE, ambiguous_garage_ids, stored_forms
from pass_billing_connector.links import Link
from pass_billing_connector.sync import sync_link

#: Three ids, one of which CONTAINS the separator and starts with another --
#: the one shape where "which garage is this line's" is ambiguous. The
#: connector refuses a covered set of this shape before any write; the pure
#: parser is exercised on it here to pin what its order does with it.
GARAGES = ("garage-a", "garage-b", "garage-a: 2")


@pytest.mark.guarantee("C13")
def test_the_pinned_line_is_the_published_one():
    assert STORED_FORM_LINE == "  at garage {garage}: {form}"


@pytest.mark.guarantee("C13")
def test_a_well_formed_answer_is_read_per_garage():
    out = ("vehicle registered to agreement ag-1\n"
           "  at garage garage-a: ab123\n  at garage garage-b: AB-123\n")
    assert stored_forms(out, GARAGES) == {"garage-a": "ab123", "garage-b": "AB-123"}


@pytest.mark.guarantee("C13")
def test_a_form_may_contain_the_separator_itself():
    out = "released\n  at garage garage-b: odd: form: here\n"
    assert stored_forms(out, GARAGES) == {"garage-b": "odd: form: here"}


@pytest.mark.guarantee("C13")
def test_a_garage_id_that_is_a_prefix_of_another_claims_no_line():
    """`garage-a: 2` begins with `garage-a` followed by the separator, so a
    first-match parse would read its line as garage-a's with the form
    `2: x1`. The longest known id is tried first, so it is not -- and that
    is exactly the guess the connector never makes: this set is refused
    before any write (below). An ordinary prefix -- no separator inside the
    id -- never needed the order: the separator itself keeps `garage-a` off
    `garage-a-2`'s line, and that set is not ambiguous."""
    out = "registered\n  at garage garage-a: 2: x1\n  at garage garage-a: x2\n"
    assert stored_forms(out, GARAGES) == {"garage-a: 2": "x1", "garage-a": "x2"}
    plain = ("garage-a", "garage-a-2")
    out = "registered\n  at garage garage-a-2: x1\n  at garage garage-a: x2\n"
    assert stored_forms(out, plain) == {"garage-a-2": "x1", "garage-a": "x2"}


@pytest.mark.guarantee("C13")
@pytest.mark.parametrize("garages, pairs", [
    (("g", "g: 2"), (("g", "g: 2"),)),
    (("garage-a", "garage-b", "garage-a: 2"), (("garage-a", "garage-a: 2"),)),
    (("g", "g: 2", "g: 2: 3"), (("g", "g: 2"), ("g", "g: 2: 3"), ("g: 2", "g: 2: 3"))),
    (("garage-a", "garage-a-2"), ()),          # a plain prefix: the separator decides
    (("g: 1", "g: 2"), ()),                    # the separator inside both, neither a prefix
    (("garage a", "garage b", "Garage Ä", "гараж-б"), ()),
    (("g", "g:2"), ()),                        # `:` without the space is not the separator
    (("g", "g :2"), ()),
])
def test_the_ambiguous_shape_is_named_and_every_other_shape_is_not(garages, pairs):
    assert ambiguous_garage_ids(garages) == pairs
    assert ambiguous_garage_ids(tuple(reversed(garages))) == pairs


@pytest.mark.guarantee("C13")
def test_an_ambiguous_covered_set_refuses_the_link_before_any_write(monkeypatch):
    """The pure half: the doors are faked, both reads name `g` and `g: 2`,
    and the connector refuses by name without a single write."""
    from test_c9_the_verdict_is_the_final_read import FakeDoors, register, shown

    pass_document = shown([("AB-123", "g"), ("AB-123", "g: 2")])
    pass_document["garages"] = ["g", "g: 2"]
    register_document = register([])
    register_document["covered_garages"] = ["g", "g: 2"]
    fake = FakeDoors([pass_document], [register_document])
    monkeypatch.setattr(sync_module, "doors", fake)
    link = Link("11111111-1111-1111-1111-111111111111", "pass-1", "g",
                "22222222-2222-2222-2222-222222222222", "ag-1")
    result = sync_link(link, AT, date(2026, 9, 16))
    assert result.refused is True and result.converged is False and result.actions == ()
    assert fake.calls == [("show-pass",), ("show-garage-register",), ("show-register",)], \
        "a refusal wrote"
    (finding,) = result.findings
    assert finding.code == "GARAGE_IDS_AMBIGUOUS" and finding.garage == "g: 2"
    assert "'g'" in finding.detail and "'g: 2'" in finding.detail


@pytest.mark.guarantee("C13")
@pytest.mark.parametrize("out", [
    "registered\n  at garage garage-z: x\n",          # a garage the read did not name
    "registered\nat garage garage-a: x\n",             # the indent is part of the line
    "registered\n  at garage garage-a: x\n  at garage garage-a: y\n",  # a garage twice
    "registered\n  AT GARAGE garage-a: x\n",
    "",
])
def test_a_line_of_another_shape_makes_the_answer_unparseable(out):
    assert stored_forms(out, GARAGES) is None


@pytest.mark.guarantee("C13")
def test_an_answer_with_no_garage_lines_is_empty_not_unparseable():
    assert stored_forms("vehicle registered to agreement ag-1\n", GARAGES) == {}


# ------------------------------------------------------------ the database


@needs_databases
@pytest.mark.guarantee("C13")
def test_the_real_door_prints_exactly_the_pinned_lines(pair):
    standard_world(pair)
    out = pair.mb_register("ag-1", "AB-123").stdout
    assert out == ("vehicle registered to agreement ag-1\n"
                   "  at garage garage-a: ab123\n"
                   "  at garage garage-b: AB-123\n")
    out = pair.mb_release("ag-1", "AB-123").stdout
    assert out == ("vehicle released from agreement ag-1\n"
                   "  at garage garage-a: ab123\n"
                   "  at garage garage-b: AB-123\n")


@needs_databases
@pytest.mark.guarantee("C13")
def test_the_door_module_reads_the_real_answer(pair, monkeypatch):
    standard_world(pair)
    for key, value in pair.env.items():
        if key.endswith("_DSN"):
            monkeypatch.setenv(key, value)
    answer = doors.register_vehicle(pair.mb_tenant, "ag-1", "AB-123",
                                    "2026-09-16T09:00:00-06:00", ("garage-a", "garage-b"))
    assert answer.outcome == "done"
    assert answer.stored == {"garage-a": "ab123", "garage-b": "AB-123"}
