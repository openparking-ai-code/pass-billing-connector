"""The guard that makes a guarantee test a guarantee: it must actually RUN.

Proving a test CAN fail is half of it. A sibling repository in this project
shipped three tests proving its presence gate was wired that skipped in every
CI run for a fortnight, on a condition nobody watched, while the build stayed
green and the file's own header claimed the opposite. A test that can quietly
not run is not a guarantee.

This is monthly-billing's mechanism, copied: a SET COMPARISON against the
registry at the end of a whole-suite run, so it catches the case a per-test
hook structurally cannot -- a module that fails to import produces no test
items at all, and a guard that only inspects items it was given will never
notice the ones it was not.

Beneath it, the database fixtures: one migrated PAIR of databases per session
(one per module, from the pinned commits), a fresh tenant in each per test.
See tests/harness.py for what each of these does and what it does not drive
through a command line.
"""

from __future__ import annotations

import os

import pytest

from _guarantees import ALLOW_ENV, GUARANTEES

_ran: set[str] = set()


def pytest_configure(config):
    config.addinivalue_line("markers", "guarantee(id): proves a registered guarantee")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when != "call":
        return
    marker = item.get_closest_marker("guarantee")
    if marker and report.passed:
        for gid in marker.args:
            _ran.add(gid)


def pytest_collection_modifyitems(config, items):
    """Every id on a mark must be in the registry -- a test claiming a
    guarantee the contract does not publish is the same defect as the
    reverse, caught here rather than at the end of the run."""
    unknown: list[str] = []
    for item in items:
        marker = item.get_closest_marker("guarantee")
        if marker:
            unknown += [
                f"{item.nodeid} -> {gid}" for gid in marker.args if gid not in GUARANTEES
            ]
    if unknown:
        raise pytest.UsageError(
            "guarantee mark(s) naming an id that is not in tests/_guarantees.py:\n  "
            + "\n  ".join(unknown)
        )


def _is_a_full_run(session) -> bool:
    """Judge a whole-suite run only. `-k`, `-m` and a file argument are all
    SELECTIONS, and a selection is not a guarantee going unproven; what the
    guard is for is the run where nothing was selected and a guarantee still
    did not execute."""
    if session.config.option.keyword or session.config.option.markexpr:
        return False
    selected = [arg for arg in session.config.args if not arg.startswith("-")]
    testpaths = session.config.getini("testpaths")
    return not selected or selected == list(testpaths)


def pytest_sessionfinish(session, exitstatus):
    if not _is_a_full_run(session):
        return
    allowed = {
        part.strip() for part in os.environ.get(ALLOW_ENV, "").split(",") if part.strip()
    }
    unaccounted = sorted(set(GUARANTEES) - _ran - allowed)
    if not unaccounted:
        return
    lines = "\n".join(f"    {gid}  {GUARANTEES[gid]}" for gid in unaccounted)
    print(
        "\nREGISTERED GUARANTEES THAT DID NOT RUN AND PASS:\n"
        f"{lines}\n"
        "\nA guarantee whose test does not run is not a guarantee. Either make it run,\n"
        f"or name the id in {ALLOW_ENV} -- which is a decision somebody writes down,\n"
        "not a default.\n"
    )
    session.exitstatus = 1


# ---------------------------------------------------------------------------
# The database pair. ONE PAIR PER SESSION, migrated from the pinned commits;
# ONE FRESH TENANT IN EACH PER TEST. Dropped at the end of the session.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def databases():
    from harness import CLUSTER_DSN, create_databases, drop_databases

    if not CLUSTER_DSN:
        pytest.skip("PASS_BILLING_CONNECTOR_TEST_DSN is not set")
    pair = create_databases(os.environ.get("PASS_BILLING_CONNECTOR_TEST_SUFFIX", "test"))
    yield pair
    drop_databases(pair)


@pytest.fixture()
def pair(databases):
    from harness import GARAGE_PASS, MONTHLY_BILLING, Pair, new_tenant

    gp, mb = databases[GARAGE_PASS], databases[MONTHLY_BILLING]
    return Pair(gp, mb, new_tenant(gp), new_tenant(mb))
