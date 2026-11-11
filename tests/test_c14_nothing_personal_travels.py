"""C14 -- nothing personal travels.

Every fixture pass carries a holder -- a name, an `example.com` address, a
phone -- because the product's passes do. None of it reaches `show-pass`
(garage-pass's G26) or `show-garage-register` (its G27), so none of it can
reach the report; and this test
renders a report from such a pass and looks, rather than trusting either
sentence. The key set is closed (C12); this is the check on the VALUES.
"""

from __future__ import annotations

import json

import pytest

from harness import AT, needs_databases, standard_world
from pass_billing_connector.report import report_keys

PERSONAL_KEYS = {"holder", "name", "phone", "email", "label", "address"}


@pytest.mark.guarantee("C14")
def test_no_published_key_is_a_personal_one():
    published = {k for keys in report_keys().values() for k in keys}
    assert published & PERSONAL_KEYS == set()


@needs_databases
@pytest.mark.guarantee("C14")
def test_a_report_from_a_pass_with_a_holder_carries_none_of_the_holder(pair, monkeypatch):
    standard_world(pair)  # the fixture pass carries holder@example.com, "A Holder"
    pair.gp_register("pass-1", "garage-a", "AB-123", "2026-09-01")
    code, report = pair.sync([pair.link()], AT, monkeypatch=monkeypatch)
    assert code == 0
    text = json.dumps(report)
    assert "holder@example.com" not in text
    assert "A Holder" not in text
    assert "Fleet" not in text  # the label
    # And the reads themselves carry nothing of the holder, measured here too:
    # the pass read, and the garage register read for its QRs.
    shown = json.dumps(pair.gp_show("pass-1", "garage-a"))
    assert "holder" not in shown and "example.com" not in shown and "Fleet" not in shown
    codes = pair.gp_run("show-garage-register", "--garage", "garage-a").stdout
    assert "holder" not in codes and "example.com" not in codes and "Fleet" not in codes


@needs_databases
@pytest.mark.guarantee("C14")
def test_the_control_the_fixture_pass_really_carries_a_holder(pair):
    """Without this, the test above proves nothing: a pass with no holder
    would pass it trivially."""
    from inspect import getsource

    from harness import Pair

    standard_world(pair)
    assert '"email": "holder@example.com", "name": "A Holder"' in getsource(Pair.gp_pass)
