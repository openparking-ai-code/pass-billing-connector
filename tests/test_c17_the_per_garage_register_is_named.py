"""C17 -- the per-garage register is compared, or it is named.

The run compares billing's rows with the pass's live IDENTITY SET rendered
through the door's per-garage forms (`expected`), and the door registers a
car at every covered garage or at none. So a pass holding a car live at some
of its garages and not at others -- a picture billing cannot be made to hold
-- converged before this guarantee existed: exit 0, no finding, while billing
covered the car at a garage the pass does not, and garage-pass's own lane at
that garage answered not covered. Measured in the outside round's L3 (538 of
1,808 converged fuzz runs with asymmetric passes).

Now it is named from the final read: `PASS_REGISTER_ASYMMETRIC`, the
identity, the garages that hold it and the garages that do not; the link
does not converge; the finding is raised after the run's own registers and
releases and causes no write of its own (the identity the first read showed
live was registered at every covered garage in step 2, as every live
identity is, and the next run makes the same register and names it again);
`expected` and the divergence lines are untouched (the L3's property
`converged => billing == expected` still holds -- the finding is a new
conjunct, not a rebuilt expectation).

THE STATE IS NOT REACHABLE THROUGH GARAGE-PASS'S OWN VERBS at the pinned
commit: a registration is written at every garage of the pass or none, an
ending frees the identity at every garage, and `revoked` -- the one state
that writes per-garage end days -- is terminal. The database test therefore
seeds it the way the L3 did, with a raw DELETE of one garage's row as the
owner, and says so here rather than pretending a door produced it.
"""

from __future__ import annotations

import pytest

from harness import AT, needs_databases, standard_world
from pass_billing_connector import sync as sync_module
from pass_billing_connector.sync import sync_link
from test_c9_the_verdict_is_the_final_read import LINK, D, FakeDoors, register, shown

CODE = "PASS_REGISTER_ASYMMETRIC"


def _delete_row_past_the_door(pair, garage: str, identity: str) -> None:
    """The raw write, as the owner: the only way the asymmetric state exists."""
    from harness import _connect

    owner = _connect(pair.gp.owner_dsn)
    owner.autocommit = True
    with owner.cursor() as cursor:
        cursor.execute(
            "DELETE FROM vehicle_registrations r USING garages g WHERE r.garage_id = g.id "
            "AND g.external_id = %s AND r.tenant_id = %s AND r.vehicle_identity = %s",
            (garage, pair.gp_tenant, identity),
        )
        assert cursor.rowcount == 1, cursor.rowcount
    owner.close()


# ---------------------------------------------------------------- pure


@pytest.mark.guarantee("C17")
def test_an_identity_live_at_a_subset_of_the_garages_is_named_and_does_not_converge(monkeypatch):
    """Billing already holds the car at both garages (a previous run); the
    pass shows it at garage-a only. Every door call says `done`, billing
    equals `expected`, and still: the finding, exit 1, nothing released."""
    pass_ = shown([("AB-123", "garage-a")])
    rows = [("garage-a", "ab123"), ("garage-b", "AB-123")]
    fake = FakeDoors([pass_, pass_], [register(rows), register(rows), register(rows)])
    monkeypatch.setattr(sync_module, "doors", fake)
    result = sync_link(LINK, AT, D)
    assert result.converged is False
    (finding,) = [f for f in result.findings if f.code == CODE]
    assert finding.identity == "AB-123"
    assert "['garage-a']" in finding.detail and "['garage-b']" in finding.detail
    # expected is what it was -- the door's forms at every covered garage --
    # and billing equals it: the finding is the only reason the link fails.
    assert [(r.garage, r.form) for r in result.expected] == rows
    assert [(r.garage, r.form) for r in result.billing] == rows
    assert [f.code for f in result.findings] == [CODE]
    assert [c for c in fake.calls if c[0] == "release-vehicle"] == []


@pytest.mark.guarantee("C17")
def test_the_control_a_symmetric_pass_is_not_named(monkeypatch):
    """The same run with the car at both garages: no finding, converged."""
    pass_ = shown([("AB-123", "garage-a"), ("AB-123", "garage-b")])
    rows = [("garage-a", "ab123"), ("garage-b", "AB-123")]
    fake = FakeDoors([pass_, pass_], [register(rows), register(rows), register(rows)])
    monkeypatch.setattr(sync_module, "doors", fake)
    result = sync_link(LINK, AT, D)
    assert result.converged is True
    assert [f.code for f in result.findings] == []


@pytest.mark.guarantee("C17")
def test_it_is_judged_on_the_final_read(monkeypatch):
    """Symmetric on the first read, asymmetric on the final: named, with
    PASS_CHANGED_DURING_RUN beside it, and not converged."""
    first = shown([("AB-123", "garage-a"), ("AB-123", "garage-b")])
    final = shown([("AB-123", "garage-b")])
    rows = [("garage-a", "ab123"), ("garage-b", "AB-123")]
    fake = FakeDoors([first, final], [register([]), register(rows), register(rows)])
    monkeypatch.setattr(sync_module, "doors", fake)
    result = sync_link(LINK, AT, D)
    assert result.converged is False
    assert [f.code for f in result.findings] == ["PASS_CHANGED_DURING_RUN", CODE]
    (finding,) = [f for f in result.findings if f.code == CODE]
    assert "['garage-b']" in finding.detail.split(" and not at ")[0]
    assert "['garage-a']" in finding.detail.split(" and not at ")[1]


# ------------------------------------------------------------ the database


@needs_databases
@pytest.mark.guarantee("C17")
@pytest.mark.parametrize("when", ["before the run", "under the run"])
def test_at_the_real_doors_the_asymmetric_state_exits_1_and_releases_nothing(
    pair, monkeypatch, when,
):
    """The car registered through garage-pass's door at both garages and
    converged into billing; then its garage-b row deleted PAST the door --
    before the run, or between the run's first and final reads. Exit 1, the
    finding naming the identity and both garage lists, billing still holding
    both rows, no release made."""
    standard_world(pair)
    pair.gp_register("pass-1", "garage-a", "AB-123", "2026-09-01")
    code, _ = pair.sync([pair.link()], AT, monkeypatch=monkeypatch)
    assert code == 0
    both = {("garage-a", "ab123"), ("garage-b", "AB-123")}
    assert pair.mb_rows("ag-1") == both

    if when == "before the run":
        _delete_row_past_the_door(pair, "garage-b", "AB-123")
    else:
        real_show_pass = sync_module.doors.show_pass
        calls = {"n": 0}

        def show_pass_then_delete(tenant, garage, pass_id):
            calls["n"] += 1
            if calls["n"] == 2:   # the final read, after the writes
                _delete_row_past_the_door(pair, "garage-b", "AB-123")
            return real_show_pass(tenant, garage, pass_id)

        monkeypatch.setattr(sync_module.doors, "show_pass", show_pass_then_delete)

    code, report = pair.sync([pair.link()], AT, monkeypatch=monkeypatch)
    assert code == 1
    (one,) = report["links"]
    assert one["converged"] is False
    assert one["live"] == {"garage-a": ["AB-123"], "garage-b": []}
    (finding,) = [f for f in one["findings"] if f["code"] == CODE]
    assert finding["identity"] == "AB-123"
    assert "live at ['garage-a'] and not at ['garage-b']" in finding["detail"]
    expected_codes = [CODE] if when == "before the run" else ["PASS_CHANGED_DURING_RUN", CODE]
    assert [f["code"] for f in one["findings"]] == expected_codes
    # Nothing released, nothing beyond the one register: billing holds both rows.
    assert [a["action"] for a in one["actions"]] == ["register"]
    assert pair.mb_rows("ag-1") == both
