"""C5 -- one verb, the instant required, the day as written, the three exits,
and links that are independent of each other.

THE DAY IS THE DATE OF THE INSTANT AS WRITTEN. `2026-09-16T23:30:00-06:00` is
`2026-09-17T05:30:00Z`; the day the connector compares with garage-pass's
days is 2026-09-16, because that is what the caller wrote -- garage-pass's
own convention for `effective_day`, and the only convention that does not
make the connector pick a zone for a pass that spans several.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from harness import AT, needs_databases, standard_world
from pass_billing_connector import cli
from pass_billing_connector.findings import EXIT_CONFIGURATION, EXIT_CONVERGED, EXIT_DIVERGED
from pass_billing_connector.sync import InstantRefused, day_of


@pytest.mark.guarantee("C5")
def test_the_verb_set_is_sync_alone():
    assert cli.VERBS == ("sync",)


@pytest.mark.guarantee("C5")
def test_the_day_is_the_date_as_written_not_converted():
    assert day_of("2026-09-16T23:30:00-06:00") == date(2026, 9, 16)
    assert day_of("2026-09-17T00:30:00+09:00") == date(2026, 9, 17)
    assert day_of("2026-09-16T09:00:00Z") == date(2026, 9, 16)


@pytest.mark.guarantee("C5")
@pytest.mark.parametrize("bad", ["2026-09-16T09:00:00", "2026-09-16", "yesterday", ""])
def test_a_naive_or_malformed_instant_is_refused(bad):
    with pytest.raises(InstantRefused):
        day_of(bad)


@pytest.mark.guarantee("C5")
def test_the_instant_is_required_and_a_naive_one_is_exit_2(tmp_path, monkeypatch):
    links = tmp_path / "links.json"
    links.write_text('{"links": []}')
    with pytest.raises(SystemExit):
        cli.main(["sync", "--links", str(links)])
    assert cli.main(["sync", "--links", str(links), "--at", "2026-09-16T09:00:00"]) == 2


@pytest.mark.guarantee("C5")
def test_the_exit_codes_are_the_published_three():
    assert (EXIT_CONVERGED, EXIT_DIVERGED, EXIT_CONFIGURATION) == (0, 1, 2)


@pytest.mark.guarantee("C5")
def test_no_links_is_a_converged_run(tmp_path, capsys):
    links = tmp_path / "links.json"
    links.write_text('{"links": []}')
    assert cli.main(["sync", "--links", str(links), "--at", AT]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report == {"at": AT, "converged": True, "day": "2026-09-16", "links": []}


# ------------------------------------------------------------ the database


@needs_databases
@pytest.mark.guarantee("C5")
def test_the_console_script_itself_answers_0_then_1_then_2(pair):
    """The three exits from the installed script, not from main(): a report
    on 0 and 1, a sentence and no report on 2."""
    standard_world(pair)
    code, report, err = pair.sync_script([pair.link()], AT)
    assert code == 0 and report["converged"] is True, (report, err)

    code, report, err = pair.sync_script([pair.link(agreement_id="ag-none")], AT)
    assert code == 1 and report["converged"] is False, (report, err)
    assert report["links"][0]["findings"][0]["code"] == "MONTHLY_BILLING_REFUSED"
    assert "NOT FOUND" in report["links"][0]["findings"][0]["detail"]

    code, report, err = pair.sync_script([pair.link()], "2026-09-16T09:00:00")
    assert code == 2 and report == {} and "offset" in err


@needs_databases
@pytest.mark.guarantee("C5")
def test_the_day_as_written_decides_which_rows_are_live(pair, monkeypatch):
    """A registration effective 2026-09-17: live at 2026-09-17T00:30+09:00
    (day 09-17 as written, still 09-16 in UTC), not live at
    2026-09-16T23:30-06:00 (day 09-16 as written, already 09-17 in UTC)."""
    standard_world(pair)
    pair.gp_register("pass-1", "garage-a", "AB-123", "2026-09-17")
    code, report = pair.sync([pair.link()], "2026-09-16T23:30:00-06:00", monkeypatch=monkeypatch)
    assert code == 0 and report["day"] == "2026-09-16"
    assert pair.mb_rows("ag-1") == set()
    code, report = pair.sync([pair.link()], "2026-09-17T00:30:00+09:00", monkeypatch=monkeypatch)
    assert code == 0 and report["day"] == "2026-09-17"
    assert pair.mb_rows("ag-1") == {("garage-a", "ab123"), ("garage-b", "AB-123")}


@needs_databases
@pytest.mark.guarantee("C5")
def test_a_module_refusal_is_a_finding_on_its_link_and_exit_1_not_2(pair, monkeypatch):
    standard_world(pair)
    wrong = "00000000-0000-0000-0000-000000000001"
    code, report = pair.sync([pair.link(billing_tenant=wrong)], AT, monkeypatch=monkeypatch)
    assert code == 1
    (finding,) = report["links"][0]["findings"]
    assert finding["code"] == "MONTHLY_BILLING_REFUSED"


@needs_databases
@pytest.mark.guarantee("C5")
def test_links_are_independent_one_broken_the_other_converges(pair, monkeypatch):
    """§5.8: two links, one broken -- the other still converges, and the run
    exits 1 for the broken one."""
    standard_world(pair)
    pair.gp_register("pass-1", "garage-a", "AB-123", "2026-09-01")
    broken = pair.link(pass_id="pass-none", agreement_id="ag-none")
    code, report = pair.sync([broken, pair.link()], AT, monkeypatch=monkeypatch)
    assert code == 1 and report["converged"] is False
    first, second = report["links"]
    assert first["converged"] is False and first["refused"] is True
    assert {f["code"] for f in first["findings"]} == {"GARAGE_PASS_REFUSED",
                                                     "MONTHLY_BILLING_REFUSED"}
    assert second["converged"] is True
    assert pair.mb_rows("ag-1") == {("garage-a", "ab123"), ("garage-b", "AB-123")}
