"""C11 -- refuse the link, writing nothing.

§5.6, each refusal of K5.1, by name, with the action list empty and billing
untouched -- and A1.4's tenant controls: a wrong tenant on either side is
THAT MODULE'S refusal, surfaced on the link by name, never an empty register.

Driven through the real modules where the modules can produce the state:
a registrar that is this module's own, garage sets that differ, a garage
stored unreadable (a raw write as the owner -- the only way one exists),
wrong tenants, and a covered set the door's printed line cannot tell apart
(`g` and `g: 2` -- both modules accept either id). Two states neither module
can be made to produce on cue -- a garage-pass row at a garage the pass does
not name (its migration 0004 RESTRICTs it) and a billing row outside the
covered set (a stored version releases them) -- are driven through faked
reads, the shapes the reads print at the pinned commits.
"""

from __future__ import annotations

from datetime import date

import pytest

from harness import AT, needs_databases, standard_world
from pass_billing_connector import sync as sync_module
from pass_billing_connector.doors import Read
from pass_billing_connector.links import Link
from pass_billing_connector.sync import sync_link
from test_c9_the_verdict_is_the_final_read import FakeDoors, register, shown

LINK = Link("11111111-1111-1111-1111-111111111111", "pass-1", "garage-a",
            "22222222-2222-2222-2222-222222222222", "ag-1")
D = date(2026, 9, 16)


def _refused_with(monkeypatch, pass_document, register_document, code):
    fake = FakeDoors([pass_document], [register_document])
    monkeypatch.setattr(sync_module, "doors", fake)
    result = sync_link(LINK, AT, D)
    assert result.refused is True and result.converged is False
    assert result.actions == ()
    assert [f.code for f in result.findings] == [code], result.findings
    assert fake.calls == [("show-pass",), ("show-garage-register",), ("show-register",)], \
        "a refusal wrote"
    return result.findings[0]


@pytest.mark.guarantee("C11")
def test_rows_outside_the_pass_garages_refuse_by_name(monkeypatch):
    document = shown([("AB-123", "garage-a")])
    document["garages_not_named"] = ["garage-z"]
    finding = _refused_with(monkeypatch, document, register([]),
                            "PASS_ROWS_OUTSIDE_ITS_GARAGES")
    assert "garage-z" in finding.detail


@pytest.mark.guarantee("C11")
def test_rows_outside_the_covered_set_refuse_by_name(monkeypatch):
    document = register([("garage-z", "x1")])
    document["garages_not_covered"] = ["garage-z"]
    finding = _refused_with(monkeypatch, shown([]), document, "REGISTER_ROWS_OUTSIDE_COVERED_SET")
    assert "garage-z" in finding.detail


@pytest.mark.guarantee("C11")
def test_an_unreadable_pass_refuses_by_name_carrying_garage_pass_own_refusal(monkeypatch):
    document = shown([])
    document["unreadable"] = {"refused": "REFUSAL_TIMEZONE_UNKNOWN", "field": "terms",
                              "detail": "planted"}
    finding = _refused_with(monkeypatch, document, register([]), "PASS_UNREADABLE")
    assert "REFUSAL_TIMEZONE_UNKNOWN" in finding.detail


@pytest.mark.guarantee("C11")
def test_a_read_that_did_not_answer_refuses_with_the_module_words(monkeypatch):
    class Silent(FakeDoors):
        def show_register(self, tenant, agreement):
            self.calls.append(("show-register",))
            return Read(None, "MONTHLY_BILLING_CONFIGURATION", "exit 1: no DSN")

    fake = Silent([shown([])], [])
    monkeypatch.setattr(sync_module, "doors", fake)
    result = sync_link(LINK, AT, D)
    assert result.refused and result.actions == ()
    assert [(f.code, f.detail) for f in result.findings] == [
        ("MONTHLY_BILLING_CONFIGURATION", "exit 1: no DSN")]


@pytest.mark.guarantee("C11")
@pytest.mark.parametrize("code, words", [
    ("GARAGE_PASS_REFUSED", '{"detail": "planted", "field": "garage", '
                            '"refused": "REFUSAL_GARAGE_NOT_FOUND"}'),
    ("GARAGE_PASS_CONFIGURATION", "exit 2: the database did not connect"),
])
def test_a_garage_register_that_did_not_answer_refuses_with_garage_pass_words(
    monkeypatch, code, words,
):
    """`show-pass` answered and `show-garage-register` did not. Without the
    garage's register the run cannot tell which cars garage-pass has replaced
    on the pass, so the pass has no live register: the link is refused before
    any write, carrying garage-pass's own words -- never read as a pass on
    which no car was replaced, which would keep a replaced car in billing."""

    class SilentGarageRegister(FakeDoors):
        def show_garage_register(self, tenant, garage):
            self.calls.append(("show-garage-register",))
            return Read(None, code, words)

    # Reads enough for a whole run, so a run that went on would fail on what
    # it did, not on a script that ran out.
    pass_ = shown([("AB-123", "garage-a"), ("AB-123", "garage-b")])
    fake = SilentGarageRegister([pass_] * 2, [register([("garage-a", "stale")])] * 3)
    monkeypatch.setattr(sync_module, "doors", fake)
    result = sync_link(LINK, AT, D)
    assert result.refused is True and result.converged is False
    assert result.actions == ()
    assert [(f.code, f.detail) for f in result.findings] == [(code, words)]
    assert fake.calls == [("show-pass",), ("show-garage-register",), ("show-register",)], \
        "a refusal wrote"


# ------------------------------------------------------------ the database


def _one_refusal(pair, monkeypatch, link, code):
    before = pair.mb_rows("ag-1") if link.get("agreement_id") == "ag-1" else None
    exit_code, report = pair.sync([link], AT, monkeypatch=monkeypatch)
    assert exit_code == 1
    (one,) = report["links"]
    assert one["refused"] is True and one["actions"] == [] and one["converged"] is False
    assert [f["code"] for f in one["findings"]] == [code], one["findings"]
    if before is not None:
        assert pair.mb_rows("ag-1") == before, "a refusal wrote"
    return one["findings"][0]


@needs_databases
@pytest.mark.guarantee("C11")
def test_a_registrar_that_is_this_module_refuses_by_name(pair, monkeypatch):
    standard_world(pair, registrar="this_module")
    pair.gp_register("pass-1", "garage-a", "AB-123", "2026-09-01")
    finding = _one_refusal(pair, monkeypatch, pair.link(), "REGISTRAR_NOT_OUTSIDE")
    assert "this_module" in finding["detail"]


@needs_databases
@pytest.mark.guarantee("C11")
def test_garage_sets_that_differ_refuse_by_name_carrying_both_sets(pair, monkeypatch):
    standard_world(pair, covered=("garage-a",))
    pair.gp_register("pass-1", "garage-a", "AB-123", "2026-09-01")
    finding = _one_refusal(pair, monkeypatch, pair.link(), "GARAGE_SETS_DIFFER")
    assert "['garage-a', 'garage-b']" in finding["detail"] and "['garage-a']" in finding["detail"]


@needs_databases
@pytest.mark.guarantee("C11")
def test_a_garage_stored_unreadable_refuses_by_name(pair, monkeypatch):
    standard_world(pair)
    pair.gp_register("pass-1", "garage-a", "AB-123", "2026-09-01")
    pair.gp_make_garage_unreadable("garage-b")
    finding = _one_refusal(pair, monkeypatch, pair.link(), "PASS_GARAGE_UNREADABLE")
    assert finding["garage"] == "garage-b"
    assert "Not/AZone" in finding["detail"] or "REFUSAL" in finding["detail"]


@needs_databases
@pytest.mark.guarantee("C11")
def test_a_wrong_garage_pass_tenant_is_garage_pass_own_refusal_never_an_empty_register(
    pair, monkeypatch,
):
    standard_world(pair)
    pair.gp_register("pass-1", "garage-a", "AB-123", "2026-09-01")
    pair.mb_register("ag-1", "Would-Go")  # an empty register would release this
    wrong = pair.link(pass_tenant="00000000-0000-0000-0000-000000000001")
    finding = _one_refusal(pair, monkeypatch, wrong, "GARAGE_PASS_REFUSED")
    assert "REFUSAL_GARAGE_NOT_FOUND" in finding["detail"]
    assert pair.mb_rows("ag-1") == {("garage-a", "wouldgo"), ("garage-b", "Would-Go")}


@needs_databases
@pytest.mark.guarantee("C11")
def test_a_wrong_billing_tenant_is_monthly_billing_own_refusal_never_an_empty_register(
    pair, monkeypatch,
):
    standard_world(pair)
    pair.gp_register("pass-1", "garage-a", "AB-123", "2026-09-01")
    wrong = pair.link(billing_tenant="00000000-0000-0000-0000-000000000001")
    finding = _one_refusal(pair, monkeypatch, wrong, "MONTHLY_BILLING_REFUSED")
    assert "NOT FOUND" in finding["detail"] and "ag-1" in finding["detail"]
    assert pair.mb_rows("ag-1") == set(), "the right tenant's register was not touched"


@needs_databases
@pytest.mark.guarantee("C11")
def test_a_covered_set_the_doors_line_cannot_tell_apart_refuses_by_name(pair, monkeypatch):
    """Both modules accept `g` and `g: 2` as garage ids. A pass over both,
    linked to an agreement covering both, is refused before any write: the
    car is live and NOT registered afterwards, and a foreign row that a
    healthy link would release is still there."""
    from harness import GARAGE_A, GARAGE_B, mb_agreement, mb_garage

    ids = ("g", "g: 2")
    for (garage_id, zone) in zip(ids, ("America/Denver", "Europe/Berlin"), strict=True):
        pair.gp_garage(garage_id, zone)
    pair.gp_pass("pass-1", ids, valid_from="2026-01-01", valid_to="2026-12-31")
    pair.mb_seed(
        tuple(mb_garage(i, z, r) for i, (_g, z, r) in zip(ids, (GARAGE_A, GARAGE_B), strict=True)),
        (mb_agreement("ag-1", "g", ids),),
    )
    pair.gp_register("pass-1", "g", "AB-123", "2026-09-01")
    pair.mb_register("ag-1", "Foreign 9")
    before = pair.mb_rows("ag-1")
    assert before == {("g", "foreign9"), ("g: 2", "Foreign 9")}
    finding = _one_refusal(pair, monkeypatch, pair.link(pass_garage="g"), "GARAGE_IDS_AMBIGUOUS")
    assert finding["garage"] == "g: 2"
    assert pair.mb_rows("ag-1") == before
