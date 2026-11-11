"""The command line: one verb.

    pass-billing-connector sync --links links.json --at 2026-09-16T09:00:00-06:00

No clock: the instant is required, ISO with an offset, and the day compared
with garage-pass's days is the date of that instant AS WRITTEN. The same
instant is passed to billing's ``register-vehicle --at``. The report is one
JSON document on stdout, sorted keys.

Exit 0: every link's billing register equals its pass's live register on the
final read. Exit 1: at least one does not. Exit 2: the connector's own
configuration -- the links document, the instant, a console script not on
PATH -- a sentence on stderr and no report. A module's refusal or
configuration sentence is never exit 2 here: it is a finding on the link it
met, in the module's own words, and the link does not converge (exit 1).
Links are independent: one broken link stops nothing for the others.

THE CONNECTOR TOUCHES REGISTRATIONS ONLY. There is one verb, it registers and
releases vehicle identities on an outside registrar's agreement, and nothing
it does can refuse an exit: no exit call exists, and no field of the report
could deny one. The pass's own access answer and billing's own coverage
answer are untouched by anything here.
"""

from __future__ import annotations

import argparse
import sys

from pass_billing_connector import doors
from pass_billing_connector.findings import EXIT_CONFIGURATION, EXIT_CONVERGED, EXIT_DIVERGED
from pass_billing_connector.links import LinksRefused, load_links
from pass_billing_connector.sync import InstantRefused, day_of, sync

VERBS: tuple[str, ...] = ("sync",)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pass-billing-connector", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("sync", help="make each linked agreement's register equal its pass's")
    s.add_argument("--links", required=True, help="the links document (JSON)")
    s.add_argument("--at", required=True, help="the instant, ISO with an offset")
    args = parser.parse_args(argv)
    try:
        day_of(args.at)
        doors.require_scripts()
        links = load_links(args.links)
    except (InstantRefused, doors.ScriptMissing, LinksRefused) as refused:
        print(str(refused), file=sys.stderr)
        return EXIT_CONFIGURATION
    report = sync(links, args.at)
    print(report.rendered())
    return EXIT_CONVERGED if report.converged else EXIT_DIVERGED


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
