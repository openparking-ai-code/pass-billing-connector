"""C9 -- the verdict is the final read.

After the run's writes both sides are read again and the verdict is taken
from THAT read, not from the calls. A door refusal on the way -- a car held
by ANOTHER agreement at a garage (§5.6) -- is recorded on its action with
the door's own sentence, the identity has no known form, and the link does
not converge, exit 1, named. A door that exited 0 with lines the connector
cannot read is recorded as `unparseable` on its action, carrying what it
printed, and the final read decides what it did. A divergence names the
garage, the form and the side that holds it. A pass that changed under the
run is named.

A REGISTER THE DOOR DID NOT ANSWER STOPS THE LINK'S RELEASES. Measured before
the rule existed (the C1 gate): a car billing already held, whose register
answered one transient failure, had every one of its rows released by the
same run -- its forms were unknown, so they looked stale. The connector
cannot tell "not registered" from "the door did not tell me"; an incomplete
picture of the desired set is never a licence to delete. THE REFUSALS ARE
CHECKED AGAIN ON THE FINAL READ: a covered set or a registrar that moved
under the run is named and the link does not converge.

THE REPORT CLAIMS NOTHING THE RUN COULD NOT LEARN. Measured at the re-gate:
with the held car's rows now kept, each was reported as a row "the pass's
live register stores nothing in" -- which the run does not know, and its own
`STORED_FORM_UNKNOWN` two lines up says it does not. A `billing_only` row
while some live identity's form is unknown names the identities whose forms
are unknown and does not call the row foreign.

A CAR MOVING BETWEEN TWO LINKED PASSES does not hold up the receiving link
until the next run: the link whose register was refused is run once more
when the other link released the car later in the same run -- and a chain is
followed: a link waiting on a car that only another link's SECOND attempt lets
go is run again too. A second attempt refused at its read wrote nothing, so
the report is the first attempt's -- not refused, its actions kept -- with the
second attempt's findings added, and their published sentences say the writes
already made stand.

The pure half fakes the two doors (`sync.doors`) so the connector's own logic
can be driven through states the real modules cannot be made to produce on
cue -- a pass changing between the first and the final read.
"""

from __future__ import annotations

import json
import os
from datetime import date

import pytest

from harness import AT, needs_databases, standard_world
from pass_billing_connector import doors as doors_module
from pass_billing_connector import sync as sync_module
from pass_billing_connector.doors import Answer, Read
from pass_billing_connector.links import Link
from pass_billing_connector.sync import sync, sync_link

LINK = Link("11111111-1111-1111-1111-111111111111", "pass-1", "garage-a",
            "22222222-2222-2222-2222-222222222222", "ag-1")
D = date(2026, 9, 16)


def shown(rows):
    return {"pass": "pass-1", "state": "active", "valid_from": "2026-01-01",
            "valid_to": "2026-12-31", "garages": ["garage-a", "garage-b"],
            "garages_not_named": [], "unreadable": None, "unreadable_garages": {},
            "registrations": [{"vehicle_identity": i, "garage": g, "effective_day": "2026-09-01",
                               "end_day": None, "ended_reason": None} for i, g in rows]}


def register(rows):
    return {"agreement": "ag-1", "version": 1, "registrar": "outside", "status": "active",
            "cancelled_effective_day": None, "home_garage": "garage-a",
            "covered_garages": ["garage-a", "garage-b"], "garages_not_covered": [],
            "registrations": [{"garage": g, "identity_normalised": f} for g, f in rows]}


class FakeDoors:
    """Two doors with a script: what each read returns, in order, and what
    the door says to each write. Records every call. The parser's own pure
    helper is the real one: the fake stands in for the doors, not for the
    reading of their line."""

    ambiguous_garage_ids = staticmethod(doors_module.ambiguous_garage_ids)

    def __init__(self, passes, registers, register_answers=None):
        self.passes, self.registers = list(passes), list(registers)
        self.register_answers = register_answers or {}
        self.calls: list[tuple] = []

    def show_pass(self, tenant, garage, pass_id):
        self.calls.append(("show-pass",))
        return Read(self.passes.pop(0), None, None)

    def show_garage_register(self, tenant, garage):
        """No QR on the pass, so no car on it was replaced."""
        self.calls.append(("show-garage-register",))
        return Read({"garage": garage, "codes": []}, None, None)

    def show_register(self, tenant, agreement):
        self.calls.append(("show-register",))
        return Read(self.registers.pop(0), None, None)

    def register_vehicle(self, tenant, agreement, identity, at, garages):
        self.calls.append(("register-vehicle", identity, at))
        folded = "".join(c for c in identity.lower() if c.isalnum())
        default = Answer("done", {"garage-a": folded, "garage-b": identity}, None)
        return self.register_answers.get(identity, default)

    def release_vehicle(self, tenant, agreement, form, garage, garages):
        self.calls.append(("release-vehicle", form, garage))
        return Answer("done", {garage: form}, None)


@pytest.mark.guarantee("C9")
def test_a_pass_that_changed_under_the_run_is_named_and_judged_on_the_final_read(monkeypatch):
    first = shown([("AB-123", "garage-a"), ("AB-123", "garage-b")])
    changed = shown([("AB-123", "garage-a"), ("AB-123", "garage-b"),
                     ("NEW-2", "garage-a"), ("NEW-2", "garage-b")])
    billing_after = register([("garage-a", "ab123"), ("garage-b", "AB-123")])
    fake = FakeDoors([first, changed], [register([]), billing_after, billing_after])
    monkeypatch.setattr(sync_module, "doors", fake)
    result = sync_link(LINK, AT, D)
    assert result.converged is False
    codes = [f.code for f in result.findings]
    assert "PASS_CHANGED_DURING_RUN" in codes
    unknown = [f for f in result.findings if f.code == "STORED_FORM_UNKNOWN"]
    assert [f.identity for f in unknown] == ["NEW-2"]
    assert result.live == {"garage-a": ("AB-123", "NEW-2"), "garage-b": ("AB-123", "NEW-2")}


@pytest.mark.guarantee("C9")
def test_a_divergence_names_garage_form_and_side(monkeypatch):
    """The final read shows a row the run did not expect and lacks one it
    did: two divergences, one per side, and the link does not converge."""
    pass_ = shown([("AB-123", "garage-a"), ("AB-123", "garage-b")])
    final = register([("garage-a", "ab123"), ("garage-b", "stray")])
    fake = FakeDoors([pass_, pass_], [register([]), register([]), final])
    monkeypatch.setattr(sync_module, "doors", fake)
    result = sync_link(LINK, AT, D)
    assert result.converged is False
    divergences = sorted((f.garage, f.form, f.side) for f in result.findings
                         if f.code == "DIVERGENCE")
    assert divergences == [("garage-b", "AB-123", "pass_only"),
                           ("garage-b", "stray", "billing_only")]
    assert [(r.garage, r.form) for r in result.expected] == [("garage-a", "ab123"),
                                                              ("garage-b", "AB-123")]
    assert [(r.garage, r.form) for r in result.billing] == [("garage-a", "ab123"),
                                                             ("garage-b", "stray")]


@pytest.mark.guarantee("C9")
def test_the_verdict_comes_from_the_final_read_not_from_the_calls(monkeypatch):
    """Every call said `done`, and the final read still disagrees: exit 1.
    A verdict taken from the calls would have said converged."""
    pass_ = shown([("AB-123", "garage-a"), ("AB-123", "garage-b")])
    fake = FakeDoors([pass_, pass_], [register([]), register([]), register([])])
    monkeypatch.setattr(sync_module, "doors", fake)
    result = sync_link(LINK, AT, D)
    assert all(a.outcome == "done" for a in result.actions)
    assert result.converged is False
    assert {f.code for f in result.findings} == {"DIVERGENCE"}


@pytest.mark.guarantee("C9")
def test_a_door_that_exited_0_unreadably_is_recorded_as_unparseable_and_the_final_read_decides(
    monkeypatch,
):
    """`doors._run` is faked to exit 0 with a line of another shape for the
    release; the register answers normally. The action says `unparseable`
    with what the door printed, nothing is guessed about what was released,
    and the final read -- the stale row still there -- decides: exit 1."""
    import subprocess

    stale = register([("garage-a", "ab123"), ("garage-b", "AB-123"), ("garage-b", "stale")])
    reads = {"show-pass": [shown([("AB-123", "garage-a"), ("AB-123", "garage-b")])] * 2,
             "show-garage-register": [{"garage": "garage-a", "codes": []}] * 2,
             "show-register": [stale] * 3}

    def run(argv):
        verb = argv[1]
        if verb in reads:
            return subprocess.CompletedProcess(argv, 0, json.dumps(reads[verb].pop(0)), "")
        if verb == "register-vehicle":
            return subprocess.CompletedProcess(
                argv, 0, "vehicle registered to agreement ag-1\n  at garage garage-a: ab123\n"
                "  at garage garage-b: AB-123\n", "")
        assert verb == "release-vehicle" and argv[-2:] == ["--garage", "garage-b"], argv
        return subprocess.CompletedProcess(argv, 0, "vehicle released from agreement ag-1\n"
                                           "  at garage garage-z: stale\n", "")

    monkeypatch.setattr(doors_module, "_run", run)
    result = sync_link(LINK, AT, D)
    (release,) = [a for a in result.actions if a.action == "release"]
    assert release.outcome == "unparseable" and release.stored == {}
    assert release.garage == "garage-b" and release.form == "stale"
    assert release.detail == ("exit 0: vehicle released from agreement ag-1\n"
                              "  at garage garage-z: stale")
    assert result.converged is False
    assert [(f.code, f.garage, f.form, f.side) for f in result.findings] == [
        ("DIVERGENCE", "garage-b", "stale", "billing_only")]


@pytest.mark.guarantee("C9")
def test_the_report_is_json_with_sorted_keys():
    from pass_billing_connector.report import Report

    rendered = Report(at=AT, day="2026-09-16", converged=True, links=()).rendered()
    assert rendered == json.dumps(json.loads(rendered), sort_keys=True, indent=2)


@pytest.mark.guarantee("C9")
@pytest.mark.parametrize("outcome, words", [
    ("refused", "exit 2: REFUSED — REFUSAL_VEHICLE_ALREADY_REGISTERED: held by ag-2"),
    ("failed", "exit 1: a store command needs --dsn or MONTHLY_BILLING_DSN."),
    ("unparseable", "exit 0: vehicle registered to agreement ag-1\n  something else"),
])
def test_a_register_the_door_did_not_answer_stops_the_links_releases(monkeypatch, outcome,
                                                                      words):
    """Billing already holds HELD-1's rows and one stale row. HELD-1's
    register does not come back `done`; FREE-2's does. NOTHING is released --
    not the stale row, and not HELD-1's rows, which would have looked stale
    with its forms unknown. The finding names the identity and the door's
    words; FREE-2's register stands; the link does not converge."""
    pass_ = shown([("HELD-1", "garage-a"), ("HELD-1", "garage-b"),
                   ("FREE-2", "garage-a"), ("FREE-2", "garage-b")])
    held = [("garage-a", "held1"), ("garage-b", "HELD-1"), ("garage-a", "stale")]
    after = register(held + [("garage-a", "free2"), ("garage-b", "FREE-2")])
    fake = FakeDoors([pass_, pass_], [register(held), after, after],
                     register_answers={"HELD-1": Answer(outcome, {}, words)})
    monkeypatch.setattr(sync_module, "doors", fake)
    result = sync_link(LINK, AT, D)
    assert [c for c in fake.calls if c[0] == "release-vehicle"] == []
    assert [(a.action, a.identity, a.outcome) for a in result.actions] == [
        ("register", "FREE-2", "done"), ("register", "HELD-1", outcome)]
    (unknown,) = [f for f in result.findings if f.code == "STORED_FORM_UNKNOWN"]
    assert unknown.identity == "HELD-1"
    assert words in unknown.detail and outcome in unknown.detail
    assert "nothing is released" in unknown.detail
    assert result.converged is False
    # The verdict still comes from the final read: every row no KNOWN form
    # accounts for is named there -- HELD-1's own two and the stale one alike,
    # because the run cannot tell them apart (HELD-1's forms are unknown, not
    # wrong) -- and each one says so; see the test below for the sentence.
    assert [(f.garage, f.form, f.side) for f in result.findings if f.code == "DIVERGENCE"] == [
        ("garage-a", "held1", "billing_only"), ("garage-a", "stale", "billing_only"),
        ("garage-b", "HELD-1", "billing_only")]


FOREIGN = "the pass's live register stores nothing in that form there"
UNKNOWN = ("no live identity whose stored form this run learned stores in it there, and the "
           "stored forms of {ids} are not known to this run, so whether this row is theirs is "
           "not known.")
#: What the published sentences say a refusal or a read that did not answer
#: means LATER in the run, when the link has already written: the writes stand.
LATER_REFUSAL = ("On a later read of the run -- the final read, or a second attempt's read -- "
                 "the writes already made stand, the link's actions list them, and the link "
                 "does not converge.")
LATER_READ = ("When it is a later read of the run -- the final read, a second attempt's read, "
              "or billing's read before the releases -- the writes already made stand, and the "
              "link's actions list them.")


@pytest.mark.guarantee("C9")
@pytest.mark.parametrize("outcome, words", [
    ("refused", "exit 2: REFUSED — REFUSAL_VEHICLE_ALREADY_REGISTERED: held by ag-2"),
    ("failed", "exit 1: a store command needs --dsn or MONTHLY_BILLING_DSN."),
    ("unparseable", "exit 0: vehicle registered to agreement ag-1\n  something else"),
])
def test_a_row_the_run_could_not_account_for_is_not_called_foreign(monkeypatch, outcome,
                                                                    words):
    """THE RE-GATE'S FINDING. HELD-1's register did not answer, so the run
    learned no form for it; billing holds HELD-1's two rows and one stale
    row, and the run cannot tell which is which -- it never reimplements
    billing's normalisation. Every one of the three is reported, and every
    one says what is true: no KNOWN form accounts for it, HELD-1's forms are
    not known, so whose it is is not known. None says the pass stores
    nothing in that form -- the sentence the re-gate read at `285fd80`.
    The control is in the same test: with every register `done`, a stray
    row IS one no live identity stores in, and the plain sentence stands."""
    pass_ = shown([("HELD-1", "garage-a"), ("HELD-1", "garage-b"),
                   ("FREE-2", "garage-a"), ("FREE-2", "garage-b")])
    held = [("garage-a", "held1"), ("garage-b", "HELD-1"), ("garage-a", "stale")]
    after = register(held + [("garage-a", "free2"), ("garage-b", "FREE-2")])
    fake = FakeDoors([pass_, pass_], [register(held), after, after],
                     register_answers={"HELD-1": Answer(outcome, {}, words)})
    monkeypatch.setattr(sync_module, "doors", fake)
    result = sync_link(LINK, AT, D)
    rows = [f for f in result.findings if f.code == "DIVERGENCE"]
    assert [(f.garage, f.form, f.side) for f in rows] == [
        ("garage-a", "held1", "billing_only"), ("garage-a", "stale", "billing_only"),
        ("garage-b", "HELD-1", "billing_only")]
    for row in rows:
        assert row.detail == (f"billing holds {row.form!r} at {row.garage!r}; "
                              + UNKNOWN.format(ids=["HELD-1"])), row.detail
        assert FOREIGN not in row.detail
        assert row.identities == ("HELD-1",)
    # The one finding that DOES say nothing was released is the one that knows it.
    (unknown,) = [f for f in result.findings if f.code == "STORED_FORM_UNKNOWN"]
    assert "nothing is released for this link" in unknown.detail

    # Control: every register answered, one stray row -- the plain sentence.
    pass_ = shown([("AB-123", "garage-a"), ("AB-123", "garage-b")])
    final = register([("garage-a", "ab123"), ("garage-b", "AB-123"), ("garage-b", "stray")])
    fake = FakeDoors([pass_, pass_], [register([]), register([]), final])
    monkeypatch.setattr(sync_module, "doors", fake)
    result = sync_link(LINK, AT, D)
    (stray,) = [f for f in result.findings if f.code == "DIVERGENCE"]
    assert stray.detail == f"billing holds 'stray' at 'garage-b'; {FOREIGN}."
    assert stray.identities == ()
    assert [f.code for f in result.findings] == ["DIVERGENCE"]


@pytest.mark.guarantee("C9")
def test_a_row_left_beside_an_identity_live_only_on_the_final_read_is_not_called_foreign(
    monkeypatch,
):
    """The OTHER path to an unknown form: NEW-2 appears on the pass under the
    run, so it was never registered and its forms are unknown. The releases
    DID run here (the stale row `gone` went), so the sentence must not say
    nothing was released -- and does not; it names NEW-2 as the identity
    whose forms are unknown, and the row `left` is not called foreign."""
    first = shown([("AB-123", "garage-a"), ("AB-123", "garage-b")])
    changed = shown([("AB-123", "garage-a"), ("AB-123", "garage-b"),
                     ("NEW-2", "garage-a"), ("NEW-2", "garage-b")])
    before = register([("garage-a", "ab123"), ("garage-b", "AB-123"), ("garage-b", "gone")])
    after = register([("garage-a", "ab123"), ("garage-b", "AB-123"), ("garage-a", "left")])
    fake = FakeDoors([first, changed], [register([]), before, after])
    monkeypatch.setattr(sync_module, "doors", fake)
    result = sync_link(LINK, AT, D)
    assert [c for c in fake.calls if c[0] == "release-vehicle"] == [
        ("release-vehicle", "gone", "garage-b")]
    codes = [f.code for f in result.findings]
    assert codes == ["PASS_CHANGED_DURING_RUN", "STORED_FORM_UNKNOWN", "DIVERGENCE"]
    (left,) = [f for f in result.findings if f.code == "DIVERGENCE"]
    assert (left.garage, left.form, left.side) == ("garage-a", "left", "billing_only")
    assert left.detail == "billing holds 'left' at 'garage-a'; " + UNKNOWN.format(ids=["NEW-2"])
    assert left.identities == ("NEW-2",)
    assert "released" not in left.detail
    assert result.converged is False


@pytest.mark.guarantee("C9")
@pytest.mark.parametrize("moved, codes", [
    ({"covered_garages": ["garage-a"]}, ["GARAGE_SETS_DIFFER"]),
    ({"registrar": "self"}, ["REGISTRAR_NOT_OUTSIDE"]),
    ({"covered_garages": ["garage-a", "garage-b", "garage-a: 2"]},
     ["GARAGE_SETS_DIFFER", "GARAGE_IDS_AMBIGUOUS"]),
    ({"garages_not_covered": ["garage-c"]}, ["REGISTER_ROWS_OUTSIDE_COVERED_SET"]),
])
def test_a_refusal_that_appears_on_the_final_read_is_named_and_the_link_does_not_converge(
    monkeypatch, moved, codes,
):
    """The first reads pass every check and the run writes; the FINAL read of
    billing shows something step 1 would have refused. Named exactly as at
    the start, and not converged -- even though the rows themselves are
    equal. The run's register stands and is listed, and the published sentence
    of each finding says so rather than that the link was refused before any
    write."""
    from pass_billing_connector.findings import FINDINGS

    pass_ = shown([("AB-123", "garage-a"), ("AB-123", "garage-b")])
    rows = [("garage-a", "ab123"), ("garage-b", "AB-123")]
    final = register(rows)
    final.update(moved)
    fake = FakeDoors([pass_, pass_], [register([]), register(rows), final])
    monkeypatch.setattr(sync_module, "doors", fake)
    result = sync_link(LINK, AT, D)
    assert result.refused is False
    assert [f.code for f in result.findings] == codes
    assert result.converged is False
    assert [(r.garage, r.form) for r in result.billing] == rows
    assert [(a.action, a.identity, a.outcome) for a in result.actions] == [
        ("register", "AB-123", "done")]
    for code in codes:
        assert LATER_REFUSAL in FINDINGS[code], FINDINGS[code]
        assert "Refused before any write." not in FINDINGS[code]


class LateRead(FakeDoors):
    """A read LATER in the run does not answer: `billing-mid`, billing's read
    before the releases; `billing-final` or `pass-final`, that side's final
    read. Every other read answers as scripted."""

    def __init__(self, late, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.late = late

    def show_pass(self, tenant, garage, pass_id):
        read = super().show_pass(tenant, garage, pass_id)
        if self.late == "pass-final" and self.calls.count(("show-pass",)) == 2:
            return Read(None, "GARAGE_PASS_CONFIGURATION", "exit 2: the database did not connect")
        return read

    def show_register(self, tenant, agreement):
        read = super().show_register(tenant, agreement)
        if (self.late, self.calls.count(("show-register",))) in {("billing-mid", 2),
                                                                 ("billing-final", 3)}:
            return Read(None, "MONTHLY_BILLING_CONFIGURATION", "exit 1: no DSN")
        return read


@pytest.mark.guarantee("C9")
@pytest.mark.parametrize("late, code", [
    ("billing-mid", "MONTHLY_BILLING_CONFIGURATION"),
    ("billing-final", "MONTHLY_BILLING_CONFIGURATION"),
    ("pass-final", "GARAGE_PASS_CONFIGURATION"),
])
def test_a_read_that_did_not_answer_after_a_write_keeps_the_write_in_the_report(
    monkeypatch, late, code,
):
    """The run registered AB-123, and then a LATER read of the run did not
    answer. The register stands in billing, so the report is not refused, the
    register is in its actions, and the module's finding carries its words.
    The finding's published sentence says the writes already made stand -- not
    that nothing was written for the link, which is true only of a first
    read."""
    from pass_billing_connector.findings import FINDINGS

    pass_ = shown([("AB-123", "garage-a"), ("AB-123", "garage-b")])
    rows = [("garage-a", "ab123"), ("garage-b", "AB-123")]
    fake = LateRead(late, [pass_, pass_], [register([]), register(rows), register(rows)])
    monkeypatch.setattr(sync_module, "doors", fake)
    result = sync_link(LINK, AT, D)
    assert result.refused is False
    assert [(a.action, a.identity, a.outcome) for a in result.actions] == [
        ("register", "AB-123", "done")]
    assert code in [f.code for f in result.findings]
    if late != "billing-mid":
        assert result.converged is False
    assert LATER_READ in FINDINGS[code], FINDINGS[code]
    assert "Nothing was written for this link." not in FINDINGS[code]


@pytest.mark.guarantee("C9")
def test_a_car_replaced_under_the_run_is_named_on_the_final_read(monkeypatch):
    """The FINAL read takes its replaced cars from the final garage register,
    not from the first: AB-123 is live on the first read and registered, and
    its QR is exit only by the final read (garage-pass's `replace-car` ran
    under the run). The final live register no longer holds it, the pass is
    named as changed under the run, and billing's AB-123 rows are named --
    the link does not converge until the next run releases them."""

    class ReplacedUnderTheRun(FakeDoors):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.garage_registers = [
                {"garage": "garage-a", "codes": [
                    {"pass": "pass-1", "state": "redeemed", "bound_identity": "AB-123",
                     "exit_only": exit_only}]}
                for exit_only in (False, True)]

        def show_garage_register(self, tenant, garage):
            self.calls.append(("show-garage-register",))
            return Read(self.garage_registers.pop(0), None, None)

    pass_ = shown([("AB-123", "garage-a"), ("AB-123", "garage-b")])
    rows = [("garage-a", "ab123"), ("garage-b", "AB-123")]
    fake = ReplacedUnderTheRun([pass_, pass_], [register([]), register(rows), register(rows)])
    monkeypatch.setattr(sync_module, "doors", fake)
    result = sync_link(LINK, AT, D)
    assert [(a.action, a.identity, a.outcome) for a in result.actions] == [
        ("register", "AB-123", "done")]
    assert result.live == {"garage-a": (), "garage-b": ()}
    assert [f.code for f in result.findings] == [
        "PASS_CHANGED_DURING_RUN", "DIVERGENCE", "DIVERGENCE"]
    assert sorted((f.garage, f.form, f.side) for f in result.findings
                  if f.code == "DIVERGENCE") == [
        ("garage-a", "ab123", "billing_only"), ("garage-b", "AB-123", "billing_only")]
    assert result.converged is False


class MovingCar(FakeDoors):
    """Two links of one run, with billing's state kept: CAR-X moves from
    pass-a to pass-b, and pass-b also holds CAR-Y. ag-a holds CAR-X's rows, so
    the door refuses CAR-X to ag-b by name until ag-a lets it go; a release
    takes the one row it names. `second` breaks pass-b's SECOND attempt: at
    its read -- `read`, garage-pass does not answer its show-pass; `registrar`,
    ag-b's registrar has moved by then, a refusal of step 1 that began between
    the attempts -- or at CAR-X's register, which comes back `failed` or
    `unparseable` (the door's words are `SECOND_WORDS`)."""

    PASSES = {"pass-a": shown([]),
              "pass-b": shown([("CAR-X", "garage-a"), ("CAR-X", "garage-b"),
                               ("CAR-Y", "garage-a"), ("CAR-Y", "garage-b")])}

    SECOND_WORDS = {"failed": "exit 1: a store command needs --dsn or MONTHLY_BILLING_DSN.",
                    "unparseable": "exit 0: vehicle registered to agreement ag-b\n  else"}

    def __init__(self, second):
        super().__init__([], [])
        self.second = second
        self.billing = {"ag-a": {("garage-a", "carx"), ("garage-b", "CAR-X")}, "ag-b": set()}
        self.reads = {"pass-b": 0, "ag-b": 0}
        self.registers_of_car_x = 0

    def show_pass(self, tenant, garage, pass_id):
        self.calls.append(("show-pass", pass_id))
        self.reads[pass_id] = self.reads.get(pass_id, 0) + 1
        if pass_id == "pass-b" and self.reads[pass_id] == 3 and self.second == "read":
            return Read(None, "GARAGE_PASS_CONFIGURATION", "exit 2: the database did not connect")
        return Read(self.PASSES[pass_id], None, None)

    def show_register(self, tenant, agreement):
        self.calls.append(("show-register", agreement))
        self.reads[agreement] = self.reads.get(agreement, 0) + 1
        document = register(sorted(self.billing[agreement]))
        document["agreement"] = agreement
        if agreement == "ag-b" and self.reads[agreement] == 3 and self.second == "registrar":
            document["registrar"] = "self"
        return Read(document, None, None)

    def register_vehicle(self, tenant, agreement, identity, at, garages):
        self.calls.append(("register-vehicle", agreement, identity))
        if (agreement, identity) == ("ag-b", "CAR-X"):
            self.registers_of_car_x += 1
            if self.registers_of_car_x == 2 and self.second in self.SECOND_WORDS:
                return Answer(self.second, {}, self.SECOND_WORDS[self.second])
        folded = "".join(c for c in identity.lower() if c.isalnum())
        stored = {("garage-a", folded), ("garage-b", identity)}
        for other, rows in self.billing.items():
            if other != agreement and stored & rows:
                return Answer("refused", {}, f"exit 2: REFUSED — "
                              f"REFUSAL_VEHICLE_ALREADY_REGISTERED: held by {other}")
        self.billing[agreement] |= stored
        return Answer("done", dict(stored), None)

    def release_vehicle(self, tenant, agreement, form, garage, garages):
        self.calls.append(("release-vehicle", agreement, form, garage))
        self.billing[agreement].discard((garage, form))
        return Answer("done", {garage: form}, None)


@pytest.mark.guarantee("C9")
@pytest.mark.parametrize("second, code, words, sentence", [
    ("read", "GARAGE_PASS_CONFIGURATION", "exit 2: the database did not connect", LATER_READ),
    ("registrar", "REGISTRAR_NOT_OUTSIDE", "'self'", LATER_REFUSAL),
])
def test_a_second_attempt_refused_at_its_read_keeps_the_first_attempts_report(
    monkeypatch, second, code, words, sentence,
):
    """pass-b's link runs first: CAR-X is refused (ag-a holds it), CAR-Y is
    registered, nothing is released. pass-a's link lets CAR-X go, so pass-b's
    link is run once more -- and that attempt is refused at its read. It wrote
    nothing, and what the first attempt wrote stands: CAR-Y is in billing. So
    the report is the first attempt's, NOT refused, its actions and rows kept,
    with the second attempt's finding after its own, and it does not
    converge. A report that said `refused` beside a register that was done
    would say the link wrote nothing when it did -- and so would the second
    attempt's finding, if its published sentence said nothing was written."""
    from pass_billing_connector.findings import FINDINGS

    fake = MovingCar(second)
    monkeypatch.setattr(sync_module, "doors", fake)
    link_a = Link(LINK.pass_tenant, "pass-a", "garage-a", LINK.billing_tenant, "ag-a")
    link_b = Link(LINK.pass_tenant, "pass-b", "garage-a", LINK.billing_tenant, "ag-b")
    report = sync((link_b, link_a), AT)
    one_b, one_a = report.links
    assert one_a.converged is True and fake.billing["ag-a"] == set()
    assert fake.reads["pass-b"] == 3, "pass-b's link was not run a second time"
    # The second attempt wrote nothing; the first attempt's register of CAR-Y stands.
    assert [c for c in fake.calls if c[0] == "register-vehicle" and c[1] == "ag-b"] == [
        ("register-vehicle", "ag-b", "CAR-X"), ("register-vehicle", "ag-b", "CAR-Y")]
    assert fake.billing["ag-b"] == {("garage-a", "cary"), ("garage-b", "CAR-Y")}
    assert one_b.refused is False
    assert one_b.converged is False and report.converged is False
    assert [(a.action, a.identity, a.outcome) for a in one_b.actions] == [
        ("register", "CAR-X", "refused"), ("register", "CAR-Y", "done")]
    assert [f.code for f in one_b.findings] == ["STORED_FORM_UNKNOWN", code]
    assert one_b.findings[0].identity == "CAR-X"
    assert words in one_b.findings[1].detail
    # The first attempt's reads and verdict: what it wrote, as its final read saw it.
    assert one_b.live == {"garage-a": ("CAR-X", "CAR-Y"), "garage-b": ("CAR-X", "CAR-Y")}
    assert [(r.garage, r.form) for r in one_b.billing] == [("garage-a", "cary"),
                                                            ("garage-b", "CAR-Y")]
    assert [(r.garage, r.form) for r in one_b.expected] == [("garage-a", "cary"),
                                                             ("garage-b", "CAR-Y")]
    # The second attempt's finding, beside a register that stands, says the writes stand.
    assert sentence in FINDINGS[code], FINDINGS[code]


@pytest.mark.guarantee("C9")
@pytest.mark.parametrize("second", ["failed", "unparseable"])
def test_a_second_attempt_whose_register_did_not_come_back_done_still_names_it(
    monkeypatch, second,
):
    """The second attempt reads and judges, so the report takes its findings
    from it -- and `STORED_FORM_UNKNOWN` stands there whenever CAR-X's register
    did not come back `done`, not only when it was refused again: here the
    door answers `failed` or `unparseable`. Nothing is released on either
    attempt, both attempts' actions are kept, and the published sentence says
    the same as the run does."""
    from pass_billing_connector.findings import FINDINGS

    fake = MovingCar(second)
    monkeypatch.setattr(sync_module, "doors", fake)
    link_a = Link(LINK.pass_tenant, "pass-a", "garage-a", LINK.billing_tenant, "ag-a")
    link_b = Link(LINK.pass_tenant, "pass-b", "garage-a", LINK.billing_tenant, "ag-b")
    report = sync((link_b, link_a), AT)
    one_b, _one_a = report.links
    assert one_b.refused is False and one_b.converged is False
    assert [(a.action, a.identity, a.outcome) for a in one_b.actions] == [
        ("register", "CAR-X", "refused"), ("register", "CAR-Y", "done"),
        ("register", "CAR-X", second), ("register", "CAR-Y", "done")]
    assert [c for c in fake.calls if c[0] == "release-vehicle" and c[1] == "ag-b"] == []
    (unknown,) = [f for f in one_b.findings if f.code == "STORED_FORM_UNKNOWN"]
    assert unknown.identity == "CAR-X"
    assert second in unknown.detail and MovingCar.SECOND_WORDS[second] in unknown.detail
    sentence = FINDINGS["STORED_FORM_UNKNOWN"]
    assert "this finding stands if that attempt's register did not come back `done` " \
           "either" in sentence
    assert "A second attempt refused at its read writes nothing: the report is then the " \
           "first attempt's, this finding included" in sentence


class Chain(MovingCar):
    """Three links of one run, with billing's state kept. pass-0 wants CAR-X,
    which ag-1 holds, and ag-0 still holds CAR-Y, which has left pass-0;
    pass-1 holds no car now, so its link lets CAR-X go; pass-2 wants CAR-Y.
    The door refuses a car held by another agreement, as in `MovingCar`."""

    PASSES = {"pass-0": shown([("CAR-X", "garage-a"), ("CAR-X", "garage-b")]),
              "pass-1": shown([]),
              "pass-2": shown([("CAR-Y", "garage-a"), ("CAR-Y", "garage-b")])}

    def __init__(self):
        super().__init__(second=None)
        self.billing = {"ag-0": {("garage-a", "cary"), ("garage-b", "CAR-Y")},
                        "ag-1": {("garage-a", "carx"), ("garage-b", "CAR-X")},
                        "ag-2": set()}


@pytest.mark.guarantee("C9")
def test_a_car_freed_only_by_another_links_second_attempt_is_followed_in_the_same_run(
    monkeypatch,
):
    """A CHAIN, in run order L0, L1, L2. L0's register of CAR-X is refused
    (ag-1 holds it), so L0 releases nothing and ag-0 keeps CAR-Y; L2's register
    of CAR-Y is refused (ag-0 holds it). L1 lets CAR-X go, so L0 is run again:
    CAR-X is registered and CAR-Y released -- by that SECOND attempt, after L2
    ran. The second attempts are tracked in run order with the first ones, so
    L2 is run again too: CAR-Y is registered to ag-2 and every link converges
    in the one run. Without that, L2 waits for the next run, and CAR-Y is in no
    agreement's billing until then."""
    fake = Chain()
    monkeypatch.setattr(sync_module, "doors", fake)
    links = tuple(Link(LINK.pass_tenant, f"pass-{n}", "garage-a", LINK.billing_tenant, f"ag-{n}")
                  for n in range(3))
    report = sync(links, AT)
    assert [c for c in fake.calls if c[0] == "register-vehicle" and c[1] == "ag-2"] == [
        ("register-vehicle", "ag-2", "CAR-Y")] * 2, "L2 was not run a second time"
    assert [one.converged for one in report.links] == [True, True, True]
    assert report.converged is True
    assert fake.billing == {"ag-0": {("garage-a", "carx"), ("garage-b", "CAR-X")},
                            "ag-1": set(),
                            "ag-2": {("garage-a", "cary"), ("garage-b", "CAR-Y")}}
    one_0, _one_1, one_2 = report.links
    assert [(a.action, a.identity or a.form, a.outcome) for a in one_0.actions] == [
        ("register", "CAR-X", "refused"), ("register", "CAR-X", "done"),
        ("release", "cary", "done"), ("release", "CAR-Y", "done")]
    assert [(a.action, a.identity, a.outcome) for a in one_2.actions] == [
        ("register", "CAR-Y", "refused"), ("register", "CAR-Y", "done")]
    assert "ag-0" in one_2.actions[0].detail
    assert one_0.findings == () and one_2.findings == ()

# ------------------------------------------------------------ the database


@needs_databases
@pytest.mark.guarantee("C9")
def test_a_car_held_by_another_agreement_is_recorded_and_named_exit_1(pair, monkeypatch):
    from harness import mb_agreement

    standard_world(pair)
    pair.mb_seed((), (mb_agreement("ag-2", "garage-a", ("garage-a",), payer="payer-2"),))
    pair.mb_register("ag-2", "HELD-1")
    pair.gp_register("pass-1", "garage-a", "held 1", "2026-09-01")
    pair.gp_register("pass-1", "garage-a", "FREE-2", "2026-09-01")
    code, report = pair.sync([pair.link()], AT, monkeypatch=monkeypatch)
    assert code == 1
    (one,) = report["links"]
    assert one["converged"] is False
    refused = [a for a in one["actions"] if a["outcome"] == "refused"]
    assert [a["identity"] for a in refused] == ["held 1"]
    assert "REFUSAL_VEHICLE_ALREADY_REGISTERED" in refused[0]["detail"]
    assert "ag-2" in refused[0]["detail"]
    unknown = [f for f in one["findings"] if f["code"] == "STORED_FORM_UNKNOWN"]
    assert [f["identity"] for f in unknown] == ["held 1"]
    # The other car converged on its own: the final read holds it.
    assert pair.mb_rows("ag-1") == {("garage-a", "free2"), ("garage-b", "FREE-2")}
    assert [f["code"] for f in one["findings"] if f["code"] == "DIVERGENCE"] == []
    # And the unanswered register stopped the releases: none was made.
    assert [a for a in one["actions"] if a["action"] == "release"] == []


@needs_databases
@pytest.mark.guarantee("C9")
def test_a_car_moving_between_two_linked_passes_does_not_hold_up_the_other_releases(
    pair, monkeypatch,
):
    """CAR-X moves from pass-a to pass-b on 09-16, and CAR-Z ends on pass-b
    that day. pass-b's link runs first: CAR-X's register is refused, because
    ag-a still holds it, so pass-b's link releases nothing. pass-a's link then
    lets CAR-X go. pass-b's link is run once more in the same run: CAR-X is
    registered and CAR-Z released -- not left in billing until the next run."""
    from harness import GARAGE_A, GARAGE_B, mb_agreement, mb_garage

    both = ("garage-a", "garage-b")
    for garage_id, zone, _rule in (GARAGE_A, GARAGE_B):
        pair.gp_garage(garage_id, zone)
    for pass_id in ("pass-a", "pass-b"):
        pair.gp_pass(pass_id, both, valid_from="2026-01-01", valid_to="2026-12-31")
    pair.mb_seed(tuple(mb_garage(g, z, r) for g, z, r in (GARAGE_A, GARAGE_B)),
                 (mb_agreement("ag-a", "garage-a", both),
                  mb_agreement("ag-b", "garage-a", both, payer="payer-2")))
    pair.gp_register("pass-a", "garage-a", "CAR-X", "2026-09-01", "2026-09-16")
    pair.gp_register("pass-b", "garage-a", "CAR-Z", "2026-09-01", "2026-09-16")
    pair.gp_register("pass-b", "garage-a", "CAR-X", "2026-09-16")
    link_a = pair.link("pass-a", agreement_id="ag-a")
    link_b = pair.link("pass-b", agreement_id="ag-b")
    code, _ = pair.sync([link_b, link_a], "2026-09-10T09:00:00-06:00", monkeypatch=monkeypatch)
    assert code == 0
    assert pair.mb_rows("ag-a") == {("garage-a", "carx"), ("garage-b", "CAR-X")}
    assert pair.mb_rows("ag-b") == {("garage-a", "carz"), ("garage-b", "CAR-Z")}

    code, report = pair.sync([link_b, link_a], AT, monkeypatch=monkeypatch)
    assert code == 0, report
    assert pair.mb_rows("ag-a") == set()
    assert pair.mb_rows("ag-b") == {("garage-a", "carx"), ("garage-b", "CAR-X")}
    one_b, one_a = report["links"]
    assert one_a["converged"] is True and one_b["converged"] is True
    assert one_b["findings"] == []
    # Both attempts are in the report: the refused register, then the second
    # attempt's register and releases.
    assert [(a["action"], a.get("identity") or a.get("form"), a["outcome"])
            for a in one_b["actions"]] == [
        ("register", "CAR-X", "refused"),
        ("register", "CAR-X", "done"),
        ("release", "carz", "done"),
        ("release", "CAR-Z", "done"),
    ]
    assert "ag-a" in one_b["actions"][0]["detail"]


@needs_databases
@pytest.mark.guarantee("C9")
def test_every_register_and_release_is_in_the_report_with_its_reason(pair, monkeypatch):
    standard_world(pair)
    pair.mb_register("ag-1", "Foreign 9")
    pair.gp_register("pass-1", "garage-a", "AB-123", "2026-09-01")
    code, report = pair.sync([pair.link()], AT, monkeypatch=monkeypatch)
    assert code == 0
    (one,) = report["links"]
    assert [(a["action"], a["reason"], a["outcome"], a["garage"]) for a in one["actions"]] == [
        ("register", "live on the day", "done", None),
        ("release", "billing holds this form; no live identity stores in it", "done", "garage-a"),
        ("release", "billing holds this form; no live identity stores in it", "done", "garage-b"),
    ]
    assert one["actions"][0]["identity"] == "AB-123"
    assert [a["form"] for a in one["actions"][1:]] == ["foreign9", "Foreign 9"]


@needs_databases
@pytest.mark.guarantee("C9")
@pytest.mark.parametrize("answer", ["failed", "unparseable"])
def test_a_held_car_whose_register_did_not_answer_keeps_its_rows_and_nothing_is_released(
    pair, monkeypatch, tmp_path, answer,
):
    """THE GATE'S CASE, BY ITS METHOD. The console script as a subprocess; a
    shim `monthly-billing` ahead of the real one on PATH intercepts exactly
    ONE call -- the first `register-vehicle` -- and forwards every other call
    to the real door. `failed` is the real door with its DSN dropped for that
    call (its own exit 1); `unparseable` is exit 0 with lines the connector
    cannot read. LIVE-1 is live on the pass and ALREADY in billing from a
    previous run, beside one stale row. After the run: billing still holds
    LIVE-1 at both garages, billing's own barrier answers COVERED at both,
    the stale row is still there (nothing was released), exit 1 with the
    finding; the next run, real door throughout, converges."""
    import shutil
    import subprocess

    standard_world(pair)
    pair.gp_register("pass-1", "garage-a", "LIVE-1", "2026-09-01")
    pair.mb_register("ag-1", "LIVE-1", AT)
    pair.mb_register("ag-1", "old1", AT)
    held = {("garage-a", "live1"), ("garage-b", "LIVE-1"), ("garage-a", "old1"),
            ("garage-b", "old1")}
    assert pair.mb_rows("ag-1") == held

    real = shutil.which("monthly-billing")
    assert real
    marker = tmp_path / "intercepted"
    shim = tmp_path / "monthly-billing"
    body = {
        "failed": f'unset MONTHLY_BILLING_DSN; exec "{real}" "$@"',
        "unparseable": 'echo "vehicle registered"; echo "  a line the connector cannot read"; '
                       'exit 0',
    }[answer]
    shim.write_text(
        "#!/bin/sh\n"
        f'if [ "$1" = "register-vehicle" ] && [ ! -e "{marker}" ]; then\n'
        f'  : > "{marker}"\n'
        f"  {body}\n"
        "fi\n"
        f'exec "{real}" "$@"\n'
    )
    shim.chmod(0o700)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")

    def covered(garage: str) -> str:
        done = pair.mb_run("covered-in-store", "--garage", garage, "--vehicle", "LIVE-1",
                           "--at", AT, check=False)
        return done.stdout.split()[0]

    code, report, err = pair.sync_script([pair.link()], AT)
    assert marker.exists(), "the shim did not intercept the register"
    assert code == 1, err
    (one,) = report["links"]
    (reg,) = [a for a in one["actions"] if a["action"] == "register"]
    assert reg["identity"] == "LIVE-1" and reg["outcome"] == answer
    assert [a for a in one["actions"] if a["action"] == "release"] == []
    (unknown,) = [f for f in one["findings"] if f["code"] == "STORED_FORM_UNKNOWN"]
    assert unknown["identity"] == "LIVE-1" and reg["detail"] in unknown["detail"]
    assert one["converged"] is False
    assert pair.mb_rows("ag-1") == held
    assert (covered("garage-a"), covered("garage-b")) == ("COVERED", "COVERED")
    # The kept rows -- LIVE-1's own two and the stale two alike -- are each
    # named, and none is called a row the pass stores nothing in: the run
    # learned no form for LIVE-1 and says exactly that on every one.
    rows = [f for f in one["findings"] if f["code"] == "DIVERGENCE"]
    assert sorted((f["garage"], f["form"]) for f in rows) == sorted(held)
    for row in rows:
        assert row["side"] == "billing_only" and row["identities"] == ["LIVE-1"]
        assert row["detail"] == (f"billing holds {row['form']!r} at {row['garage']!r}; "
                                 + UNKNOWN.format(ids=["LIVE-1"])), row["detail"]
        assert FOREIGN not in row["detail"]

    # The next run, the real door throughout: the stale row goes, LIVE-1 stays.
    monkeypatch.setenv("PATH", os.environ["PATH"].split(":", 1)[1])
    code, report, err = pair.sync_script([pair.link()], AT)
    assert code == 0, err
    assert [(a["action"], a["form"], a["garage"]) for a in report["links"][0]["actions"]] == [
        ("register", None, None), ("release", "old1", "garage-a"), ("release", "old1", "garage-b")]
    assert pair.mb_rows("ag-1") == {("garage-a", "live1"), ("garage-b", "LIVE-1")}
    assert (covered("garage-a"), covered("garage-b")) == ("COVERED", "COVERED")
    assert subprocess.run(["which", "monthly-billing"], capture_output=True,
                          text=True).stdout.strip() == real


@needs_databases
@pytest.mark.guarantee("C9")
@pytest.mark.parametrize("covered_after", [("garage-a",), ("garage-a", "garage-b", "garage-c")])
def test_a_covered_set_that_moved_under_the_run_is_named_on_the_final_read(
    pair, monkeypatch, covered_after,
):
    """Billing's operator stores version 2 of the agreement -- fewer garages,
    or more -- between the connector's first read and its first write. The
    first read passed; the final read shows sets that differ, and the link
    is named `GARAGE_SETS_DIFFER` and does not converge, exit 1. The next
    run refuses it by name before any write."""
    from harness import mb_agreement, mb_garage

    standard_world(pair)
    if "garage-c" in covered_after:
        pair.mb_seed((mb_garage("garage-c", "Pacific/Auckland", "exact"),), ())
    pair.gp_register("pass-1", "garage-a", "LIVE-1", "2026-09-01")
    pair.mb_register("ag-1", "old1", AT)
    original = doors_module._run
    reads = {"n": 0}

    def run_and_revise(argv):
        done = original(argv)
        if argv[1] == "show-register":
            reads["n"] += 1
            if reads["n"] == 1:
                version_2 = mb_agreement("ag-1", "garage-a", covered_after)
                version_2["version"] = 2
                pair.mb_revise(version_2)
        return done

    monkeypatch.setattr(doors_module, "_run", run_and_revise)
    code, report = pair.sync([pair.link()], AT, monkeypatch=monkeypatch)
    assert code == 1
    (one,) = report["links"]
    assert one["refused"] is False and one["converged"] is False
    assert "GARAGE_SETS_DIFFER" in [f["code"] for f in one["findings"]]
    monkeypatch.setattr(doors_module, "_run", original)
    code, report = pair.sync([pair.link()], AT, monkeypatch=monkeypatch)
    assert code == 1
    (one,) = report["links"]
    assert one["refused"] is True and one["actions"] == []
    assert [f["code"] for f in one["findings"]] == ["GARAGE_SETS_DIFFER"]
