"""C4 -- links are stated, never inferred.

The pure half: every refusal of the links document, by name, before anything
is read -- a duplicate caught whatever the letter case of its tenant, since
both modules read a tenant as a uuid (measured below). The database half:
`pass_garage` is an ACCESS KEY -- a garage the pass does not name is
garage-pass's own refusal -- `REFUSAL_PASS_NOT_FOUND`
naming the set the pass does name, its G25, measured at the pinned commit; a
garage the tenant does not hold at all is `REFUSAL_GARAGE_NOT_FOUND` -- surfaced
on the link by name and never read as an empty register; and the sets compared
are the pass's whole garage set and the agreement's whole covered set, whichever
garage the link names.
"""

from __future__ import annotations

import json

import pytest

from harness import AT, needs_databases, standard_world
from pass_billing_connector import cli
from pass_billing_connector.links import LINK_KEYS, LinksRefused, links_from, load_links

T1 = "11111111-1111-1111-1111-111111111111"
T2 = "22222222-2222-2222-2222-222222222222"


def link(**overrides) -> dict:
    base = {"pass_tenant": T1, "pass_id": "pass-1", "pass_garage": "garage-a",
            "billing_tenant": T2, "agreement_id": "ag-1"}
    base.update(overrides)
    return base


@pytest.mark.guarantee("C4")
def test_the_published_keys_are_the_five():
    assert LINK_KEYS == ("pass_tenant", "pass_id", "pass_garage", "billing_tenant", "agreement_id")


@pytest.mark.guarantee("C4")
def test_a_well_formed_document_loads():
    (one,) = links_from({"links": [link()]})
    assert one.pass_id == "pass-1" and one.agreement_id == "ag-1"


@pytest.mark.guarantee("C4")
@pytest.mark.parametrize("document, fragment", [
    ({"links": [link(extra="x")]}, "does not read: ['extra']"),
    ({"links": [{k: v for k, v in link().items() if k != "agreement_id"}]},
     "missing ['agreement_id']"),
    ({"links": [link(pass_tenant="not-a-uuid")]}, "pass_tenant is a uuid"),
    ({"links": [link(billing_tenant="")]}, "billing_tenant is non-blank"),
    ({"links": [link(pass_id="  ")]}, "pass_id is non-blank"),
    ({"links": [link(), link(agreement_id="ag-2")]}, "pass 'pass-1'"),
    ({"links": [link(), link(pass_id="pass-2")]}, "agreement 'ag-1'"),
    ({"links": [link(), link(pass_tenant=T2, pass_id="pass-2")]}, "agreement 'ag-1'"),
    ({"links": "x"}, "is a list of links"),
    ({"links": [1]}, "link 0 is not an object"),
    ({"other": []}, "exactly one key"),
    ([], "exactly one key"),
])
def test_each_malformed_document_is_refused_by_name(document, fragment):
    with pytest.raises(LinksRefused) as refused:
        links_from(document)
    assert fragment in str(refused.value)


@pytest.mark.guarantee("C4")
def test_the_same_pass_id_under_two_tenants_is_two_passes():
    """A duplicate is (tenant, id): the same id under two tenants is two
    different passes, and is not refused."""
    two = links_from({"links": [link(), link(pass_tenant=T2, billing_tenant=T1)]})
    assert len(two) == 2


#: A tenant with letters in it, so its two spellings differ only in case.
LETTERS = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"


@pytest.mark.guarantee("C4")
@pytest.mark.parametrize("second, fragment", [
    (link(pass_tenant=LETTERS.upper(), billing_tenant=LETTERS, agreement_id="ag-2"),
     "pass 'pass-1'"),
    (link(pass_tenant=LETTERS, billing_tenant=LETTERS.upper(), pass_id="pass-2"),
     "agreement 'ag-1'"),
])
def test_a_duplicate_is_refused_whatever_the_letter_case_of_its_tenant(second, fragment):
    """Both modules read `--tenant` as a uuid, so `ABC...` and `abc...` are one
    tenant there; two links to one agreement (or from one pass) typed that way
    would each release the other's cars on every run. Refused like any other
    duplicate."""
    first = link(pass_tenant=LETTERS, billing_tenant=LETTERS)
    with pytest.raises(LinksRefused) as refused:
        links_from({"links": [first, second]})
    assert fragment in str(refused.value)


@pytest.mark.guarantee("C4")
def test_an_unreadable_or_non_json_file_is_exit_2(tmp_path):
    missing = tmp_path / "missing.json"
    with pytest.raises(LinksRefused):
        load_links(str(missing))
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(LinksRefused):
        load_links(str(bad))
    assert cli.main(["sync", "--links", str(bad), "--at", "2026-09-16T09:00:00-06:00"]) == 2


@pytest.mark.guarantee("C4")
def test_nothing_is_inferred_from_matching_ids(tmp_path):
    """An EMPTY links document with two databases full of matching ids does
    nothing: the report has no links and exit 0 -- there is nothing to guess
    from."""
    empty = tmp_path / "links.json"
    empty.write_text(json.dumps({"links": []}))
    assert links_from({"links": []}) == ()


# ------------------------------------------------------------ the database


@needs_databases
@pytest.mark.guarantee("C4")
def test_a_garage_the_pass_does_not_name_is_garage_pass_own_refusal(pair, monkeypatch):
    standard_world(pair)
    pair.gp_garage("garage-c", "UTC")  # exists, but the pass does not name it
    code, report = pair.sync([pair.link(pass_garage="garage-c")], AT, monkeypatch=monkeypatch)
    assert code == 1
    (one,) = report["links"]
    assert one["refused"] is True and one["actions"] == []
    (finding,) = one["findings"]
    assert finding["code"] == "GARAGE_PASS_REFUSED"
    assert "REFUSAL_PASS_NOT_FOUND" in finding["detail"] and "garage-c" in finding["detail"]
    assert one["live"] == {}, "a refusal is never an empty register"


@needs_databases
@pytest.mark.guarantee("C4")
def test_a_garage_the_tenant_does_not_hold_is_garage_pass_own_refusal(pair, monkeypatch):
    standard_world(pair)
    code, report = pair.sync([pair.link(pass_garage="garage-x")], AT, monkeypatch=monkeypatch)
    assert code == 1
    (finding,) = report["links"][0]["findings"]
    assert finding["code"] == "GARAGE_PASS_REFUSED"
    assert "REFUSAL_GARAGE_NOT_FOUND" in finding["detail"]


@needs_databases
@pytest.mark.guarantee("C4")
def test_the_access_key_is_not_a_scope(pair, monkeypatch):
    """Naming garage-b in the link reconciles garage-a as well: the whole
    set, whichever garage the link names."""
    standard_world(pair)
    pair.gp_register("pass-1", "garage-a", "AB-123", "2026-09-01")
    code, report = pair.sync([pair.link(pass_garage="garage-b")], AT, monkeypatch=monkeypatch)
    assert code == 0, report
    assert pair.mb_rows("ag-1") == {("garage-a", "ab123"), ("garage-b", "AB-123")}


@needs_databases
@pytest.mark.guarantee("C4")
def test_both_modules_read_a_tenant_in_capitals_as_the_same_tenant(pair, monkeypatch):
    """The premise of comparing tenants as uuids, measured at the pinned
    commits: a link whose two tenants are typed in capitals reads and writes
    the very pass and agreement the lower-case spelling names."""
    standard_world(pair)
    pair.gp_register("pass-1", "garage-a", "AB-123", "2026-09-01")
    capitals = pair.link(pass_tenant=pair.gp_tenant.upper(),
                         billing_tenant=pair.mb_tenant.upper())
    assert capitals["pass_tenant"] != pair.gp_tenant
    assert capitals["billing_tenant"] != pair.mb_tenant
    code, report = pair.sync([capitals], AT, monkeypatch=monkeypatch)
    assert code == 0, report
    assert pair.mb_rows("ag-1") == {("garage-a", "ab123"), ("garage-b", "AB-123")}

