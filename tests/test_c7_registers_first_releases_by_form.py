"""C7 -- registers first, releases by stored form, never by raw identity; and
the connector never reimplements billing's normalisation.

§5.1: a pass over two garages whose billing identity rules DIFFER (folded at
garage-a, exact at garage-b -- tests/test_fixture_axes.py holds the control),
linked to an agreement covering the same two: the first sync registers; a
second sync is a no-op -- exit 0, no actions.

§5.2: a car swap, old ended and new started the same day, including a swap
whose two plates fold to ONE form at garage-a -- in both directions. The
door's UNNAMED release reaches every covered garage by identity, and cannot
take the stale row alone (measured here, at the pinned commit: asked to
release the stale exact form `AB123` at garage-b, whose folded form `ab123`
is the live car's at garage-a, billing refuses the whole release by name and
writes nothing). The connector never calls it: every release names the one
garage that stores the form, so the stale row goes, the live row stays, and
billing answers COVERED for the new car at BOTH garages after EVERY door
call of the run.

§5.5: a foreign row written into billing through the door by something else
is released and reported.

And the precondition, measured at the door rather than assumed: billing's
normalisation is idempotent under both rules -- a form registered as an
identity comes back as itself -- which is what makes a release by form sound.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from harness import AT, needs_databases, standard_world
from pass_billing_connector import doors

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "pass_billing_connector"

#: The shapes a reimplementation of the folded rule takes, as AST. A `.lower()`
#: call and an `.isalnum()` call in ONE expression is the rule; either alone
#: is ordinary string handling and is not forbidden.
def _has_the_folded_rule(tree: ast.AST) -> list[str]:
    hits: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.GeneratorExp, ast.ListComp, ast.Call)):
            continue
        text = ast.unparse(node)
        if ".lower()" in text and ".isalnum()" in text:
            hits.append(text)
    return hits


def reimplementations() -> dict[str, list[str]]:
    return {
        path.name: hits
        for path in sorted(SRC.glob("*.py"))
        if (hits := _has_the_folded_rule(ast.parse(path.read_text())))
    }


@pytest.mark.guarantee("C7")
def test_the_package_holds_no_copy_of_billings_normalisation():
    assert reimplementations() == {}, reimplementations()


@pytest.mark.guarantee("C7")
def test_the_scan_finds_a_planted_copy(tmp_path):
    """The control on the scan, against the exact spelling billing uses."""
    planted = tmp_path / "planted.py"
    planted.write_text(
        "def normalise(identity):\n"
        "    return ''.join(c for c in identity.lower() if c.isalnum())\n"
    )
    assert _has_the_folded_rule(ast.parse(planted.read_text()))


# ------------------------------------------------------------ the database


@needs_databases
@pytest.mark.guarantee("C7")
def test_first_sync_registers_and_a_second_is_a_no_op(pair, monkeypatch):
    standard_world(pair)
    pair.gp_register("pass-1", "garage-a", "AB-123", "2026-09-01")
    pair.gp_register("pass-1", "garage-a", "cd 456", "2026-09-10")
    code, report = pair.sync([pair.link()], AT, monkeypatch=monkeypatch)
    assert code == 0, report
    (one,) = report["links"]
    # garage-pass hands out each plate in its one normal form; the exact
    # garage stores that text as given, the folded garage folds it.
    assert [(a["action"], a["identity"], a["outcome"]) for a in one["actions"]] == [
        ("register", "AB123", "done"), ("register", "CD456", "done")]
    assert one["actions"][0]["stored"] == {"garage-a": "ab123", "garage-b": "AB123"}
    assert one["actions"][1]["stored"] == {"garage-a": "cd456", "garage-b": "CD456"}
    assert pair.mb_rows("ag-1") == {("garage-a", "ab123"), ("garage-b", "AB123"),
                                    ("garage-a", "cd456"), ("garage-b", "CD456")}
    assert one["expected"] == [{"form": f, "garage": g} for g, f in sorted(pair.mb_rows("ag-1"))]

    code, report = pair.sync([pair.link()], AT, monkeypatch=monkeypatch)
    assert code == 0
    (one,) = report["links"]
    # Idempotent AT THE DOOR: the registers are made again and are no-ops
    # there; nothing is released, nothing changes.
    assert all(a["action"] == "register" and a["outcome"] == "done" for a in one["actions"])
    assert one["findings"] == []
    assert pair.mb_rows("ag-1") == {("garage-a", "ab123"), ("garage-b", "AB123"),
                                    ("garage-a", "cd456"), ("garage-b", "CD456")}


@needs_databases
@pytest.mark.guarantee("C7")
def test_a_car_swap_releases_the_old_and_keeps_the_new(pair, monkeypatch):
    standard_world(pair)
    pair.gp_register("pass-1", "garage-a", "OLD-1", "2026-09-01")
    assert pair.sync([pair.link()], "2026-09-10T09:00:00-06:00", monkeypatch=monkeypatch)[0] == 0
    pair.gp_end("pass-1", "garage-a", "OLD-1", "2026-09-16")
    pair.gp_register("pass-1", "garage-a", "NEW-2", "2026-09-16")
    code, report = pair.sync([pair.link()], AT, monkeypatch=monkeypatch)
    assert code == 0, report
    (one,) = report["links"]
    # TWO releases, one per stale row, each naming its garage and passing the
    # form THAT garage stored; each answer is the one row it took.
    assert [(a["action"], a.get("identity") or a.get("form"), a["garage"])
            for a in one["actions"]] == [
        ("register", "NEW2", None), ("release", "0ld1", "garage-a"),
        ("release", "0LD1", "garage-b")]
    assert one["actions"][1]["stored"] == {"garage-a": "0ld1"}
    assert one["actions"][2]["stored"] == {"garage-b": "0LD1"}
    assert one["findings"] == []
    assert pair.mb_rows("ag-1") == {("garage-a", "new2"), ("garage-b", "NEW2")}


def _covered(pair, identity: str) -> dict[str, int]:
    """Billing's own barrier, per garage: exit 0 COVERED, 1 NOT COVERED."""
    return {
        garage: pair.mb_run("covered-in-store", "--garage", garage, "--vehicle", identity,
                            "--at", AT, check=False).returncode
        for garage in ("garage-a", "garage-b")
    }


#: The case in both directions. The stale row is at the EXACT garage and its
#: text, folded, is the live car's form at the FOLDED garage -- the one shape
#: the door's unnamed release cannot take without taking the live row. The
#: two plates are two cars to garage-pass (its normal form keeps the slash)
#: and one form to billing's folded rule (letters and digits alone).
SWAPS = {
    "stale-is-the-folded-text": ("AB123", "AB/123"),   # stale b:AB123; live a:ab123 = AB/123's
    "stale-is-the-slashed-text": ("AB/123", "AB123"),  # stale b:AB/123; live a:ab123 = AB123's
}


@needs_databases
@pytest.mark.guarantee("C7")
def test_the_doors_unnamed_release_would_take_the_live_row(pair):
    """THE PREMISE, measured at the pinned commit rather than assumed: the
    unnamed release the connector never calls. Stale b:`AB123` beside the
    live `AB/123`; the unnamed release of `AB123` would take a:`ab123` -- the
    live car's -- so billing refuses it by name and writes nothing: the stale
    row cannot go that way. Only the release that names garage-b takes it,
    and the live car stays COVERED at both garages."""
    standard_world(pair)
    pair.mb_register("ag-1", "AB/123")
    pair.mb_register("ag-1", "AB123")  # a: already ab123; b: AB123 -- the stale row
    before = {("garage-a", "ab123"), ("garage-b", "AB/123"), ("garage-b", "AB123")}
    assert pair.mb_rows("ag-1") == before
    assert _covered(pair, "AB/123") == {"garage-a": 0, "garage-b": 0}
    done = pair.mb_release("ag-1", "AB123", check=False)  # unnamed: every covered garage
    assert done.returncode == 2, (done.stdout, done.stderr)
    assert "REFUSAL_RELEASE_AMBIGUOUS_ACROSS_GARAGES" in done.stdout + done.stderr
    assert pair.mb_rows("ag-1") == before
    assert _covered(pair, "AB/123") == {"garage-a": 0, "garage-b": 0}
    # The named release takes the one row.
    out = pair.mb_release("ag-1", "AB123", "garage-b").stdout
    assert out.splitlines()[1:] == ["  at garage garage-b: AB123"]
    assert pair.mb_rows("ag-1") == {("garage-a", "ab123"), ("garage-b", "AB/123")}
    assert _covered(pair, "AB/123") == {"garage-a": 0, "garage-b": 0}


@needs_databases
@pytest.mark.guarantee("C7")
@pytest.mark.parametrize("old, new", list(SWAPS.values()), ids=list(SWAPS))
def test_a_swap_whose_plates_fold_to_one_form_never_touches_the_new_cars_row(
    pair, monkeypatch, old, new,
):
    """The stale row goes, the live row stays, and billing answers COVERED for
    the new car at both garages after EVERY door call of the run -- there is
    no window. The instrument wraps the door: after each write it asks
    billing's own barrier at both garages."""
    standard_world(pair)
    pair.gp_register("pass-1", "garage-a", old, "2026-09-01")
    assert pair.sync([pair.link()], "2026-09-10T09:00:00-06:00", monkeypatch=monkeypatch)[0] == 0
    pair.gp_end("pass-1", "garage-a", old, "2026-09-16")
    pair.gp_register("pass-1", "garage-a", new, "2026-09-16")
    stale_at_b = old  # the exact garage stores the text as given
    assert pair.mb_rows("ag-1") == {("garage-a", "ab123"), ("garage-b", stale_at_b)}

    after_each_write: list[tuple[str, dict[str, int]]] = []
    real_run = doors._run

    def run_then_ask_the_barrier(argv):
        done = real_run(argv)
        if argv[1] in ("register-vehicle", "release-vehicle"):
            after_each_write.append((argv[1], _covered(pair, new)))
        return done

    monkeypatch.setattr(doors, "_run", run_then_ask_the_barrier)
    code, report = pair.sync([pair.link()], AT, monkeypatch=monkeypatch)
    assert code == 0, report
    (one,) = report["links"]
    assert pair.mb_rows("ag-1") == {("garage-a", "ab123"), ("garage-b", new)}
    assert [(a["action"], a.get("identity") or a.get("form"), a["garage"], a["reason"])
            for a in one["actions"]] == [
        ("register", new, None, "live on the day"),
        ("release", stale_at_b, "garage-b",
         "billing holds this form; no live identity stores in it"),
    ]
    assert one["actions"][1]["stored"] == {"garage-b": stale_at_b}
    assert one["findings"] == []
    # COVERED at both garages after the register AND after the release: the
    # named release reached garage-b alone.
    assert after_each_write == [("register-vehicle", {"garage-a": 0, "garage-b": 0}),
                                ("release-vehicle", {"garage-a": 0, "garage-b": 0})]


@needs_databases
@pytest.mark.guarantee("C7")
def test_a_foreign_row_written_through_the_door_is_released_and_reported(pair, monkeypatch):
    standard_world(pair)
    pair.gp_register("pass-1", "garage-a", "AB-123", "2026-09-01")
    pair.mb_register("ag-1", "Foreign 9")  # something else, through the door
    # Billing's folded rule reads O as 0 and I as 1.
    assert pair.mb_rows("ag-1") == {("garage-a", "f0re1gn9"), ("garage-b", "Foreign 9")}
    code, report = pair.sync([pair.link()], AT, monkeypatch=monkeypatch)
    assert code == 0, report
    (one,) = report["links"]
    releases = [a for a in one["actions"] if a["action"] == "release"]
    # One release per stale ROW, at its garage, by the form that garage stored.
    assert [(a["garage"], a["form"], a["stored"]) for a in releases] == [
        ("garage-a", "f0re1gn9", {"garage-a": "f0re1gn9"}),
        ("garage-b", "Foreign 9", {"garage-b": "Foreign 9"}),
    ]
    assert all(a["reason"] == "billing holds this form; no live identity stores in it"
               for a in releases)
    assert pair.mb_rows("ag-1") == {("garage-a", "ab123"), ("garage-b", "AB123")}


@needs_databases
@pytest.mark.guarantee("C7")
@pytest.mark.parametrize("identity", ["AB-123", " ab 123 ", "İSTANBUL 34", "ΑΣ 12", "ẞ1",
                                      "ＡＢＣ１２３", "ÄÖ-9"])
def test_normalisation_is_idempotent_at_the_door_under_both_rules(pair, identity):
    """A form registered as an identity comes back as itself, at the folded
    garage and at the exact one -- the precondition of releasing by form."""
    standard_world(pair)
    first = pair.mb_register("ag-1", identity).stdout.splitlines()[1:]
    forms = dict(line.strip()[len("at garage "):].split(": ", 1) for line in first)
    assert set(forms) == {"garage-a", "garage-b"}
    for garage, form in forms.items():
        again = pair.mb_register("ag-1", form).stdout.splitlines()[1:]
        forms_again = dict(line.strip()[len("at garage "):].split(": ", 1) for line in again)
        assert forms_again[garage] == form, (identity, garage, form, forms_again)
        # Put the world back: each row this register wrote, at its own garage.
        for at_garage, written in forms_again.items():
            pair.mb_release("ag-1", written, at_garage)


@needs_databases
@pytest.mark.guarantee("C7")
def test_releases_pass_forms_never_a_raw_identity(pair, monkeypatch):
    """Billing holds `Foreign 9` at garage-b (exact) and `f0re1gn9` at garage-a
    (folded), and the pass is empty. Each release passes a FORM billing
    printed back -- never a raw identity the connector made up -- at the
    garage that printed it: the stale rows are walked sorted as (garage,
    form), garage-a's `f0re1gn9` first."""
    standard_world(pair)
    pair.mb_register("ag-1", "Foreign 9")
    code, report = pair.sync([pair.link()], AT, monkeypatch=monkeypatch)
    assert code == 0
    (one,) = report["links"]
    assert [(a["garage"], a["form"]) for a in one["actions"]] == [
        ("garage-a", "f0re1gn9"), ("garage-b", "Foreign 9")]
    assert all(a["identity"] is None for a in one["actions"])
    assert pair.mb_rows("ag-1") == set()


@needs_databases
@pytest.mark.guarantee("C7")
def test_a_stale_folded_form_alone_is_released_by_that_form(pair, monkeypatch):
    """The other order: only the folded-looking text `foreign9` is left, at
    garage-b (garage-a's row already gone), so THAT is the form passed back."""
    standard_world(pair)
    pair.mb_register("ag-1", "Foreign 9")
    pair.mb_release("ag-1", "Foreign 9")   # fans out: takes both rows
    pair.mb_register("ag-1", "foreign9")   # a: f0re1gn9, b: foreign9
    pair.mb_release("ag-1", "Foreign 9", "garage-a")   # a: f0re1gn9 goes (folds)
    assert pair.mb_rows("ag-1") == {("garage-b", "foreign9")}
    code, report = pair.sync([pair.link()], AT, monkeypatch=monkeypatch)
    assert code == 0
    (one,) = report["links"]
    assert [(a["garage"], a["form"], a["stored"]) for a in one["actions"]] == [
        ("garage-b", "foreign9", {"garage-b": "foreign9"})]
    assert pair.mb_rows("ag-1") == set()
