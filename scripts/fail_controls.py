#!/usr/bin/env python3
"""Every guarantee, proven able to FAIL.

A test that has never failed is a decoration. For each registered guarantee this
script breaks the thing the guarantee guards, runs that guarantee's tests in a
fresh interpreter, and requires them to go RED. If a test stays green with its
subject broken, it was not measuring its subject and this script says so.

    python scripts/fail_controls.py            # every control
    python scripts/fail_controls.py G2 G9      # a subset
    python scripts/fail_controls.py --anchors  # anchors only, in a second

**The anchor pre-flight.** ``--anchors`` counts every plant's ``from`` string in
its file without running a single test. An anchor is a string in a source file,
and editing the line it sits on silently retires the control that depends on it --
a sibling repository in this project had five dead controls killed exactly that
way, by a fix round that edited the anchor lines and reported the result as
controls that worked. The pre-flight answers that whole failure mode in a second
where the full run takes a minute, and run against an older tree it is its own
positive control.

**Restores are written back, never `git checkout`.** Each plant is a context
manager whose ``finally`` writes the original bytes and verifies them. `checkout`
has been broken twice on this project and would take a co-resident session's
uncommitted work with it.

**AND A CONTROL THAT REPORTS UNMEASURED IS REPORTING ON THE RUNNER.** If a target
is already red before anything is planted, or ran no tests at all, this says
UNMEASURED rather than counting a pass -- because a suite that cannot run cannot
tell you whether a control fired. Check the runner (is the package installed? is
a database reachable for the ones that need one?) before reading anything into
the subject.

**A TARGET WHOSE TESTS ALL SKIP IS REPORTED "NOT A CONTROL", NOT UNMEASURED, AND
THAT IS THIS SCRIPT'S OWN LIMIT RATHER THAN A JUDGEMENT.** `_NOTHING_RAN` matches
"0 passed", "no tests ran" and "collected 0 items"; an all-skipped target prints
none of those -- it prints "8 skipped" -- so the run proceeds, the target stays
green with its subject broken, and the verdict is DEAD. That is what happens to
a database-backed control on a machine with no database. The exit status is 1 either way, so nothing
goes falsely green; the word is simply the wrong one, and it is recorded here
rather than in a comment that promises otherwise. Read a DEAD verdict on a
database-backed control as "check whether you gave it a database" first.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src"))

from _guarantees import GUARANTEES  # noqa: E402
from plant import planted, resolve  # noqa: E402


def source(*lines: str) -> str:
    """A block of source code, one argument per line.

    An anchor is frequently several lines long, and written as a single literal
    with escaped newlines it becomes a three-hundred-character line that nobody
    can read and no diff can review. Same string, legible.
    """
    return "\n".join(lines)


def guarantee_of(control_id: str) -> str:
    """The guarantee a control id names. ``G2/instants`` -> ``G2``.

    One guarantee can need more than one plant, and G2's does: the DST claim and
    the proration claim fail in different code, and a single plant carrying both
    would go red if it caught EITHER -- which is the arrangement that lets one
    half sit unmeasured behind the other.
    """
    return control_id.split("/", 1)[0]


#: control id -> (test target, source file, anchor, replacement, what breaks)
CONTROLS: dict[str, tuple[str, str, str, str, str]] = {
    "C1": (
        "tests/test_guarantee_guard.py",
        "tests/test_guarantee_guard.py",
        "        elif name not in UNGUARANTEED_MODULES:",
        "        elif False:  # PLANTED: a module with no mark is accepted",
        "a test module carrying no guarantee mark stops being reported, which is "
        "the hole that hid 16 tests in monthly-billing and 21 in a sibling "
        "repository -- skip or delete such a module and every gate stays green",
    ),
    "C2": (
        "tests/test_contract_is_generated.py",
        "scripts/generate_contract.py",
        '        f"That is {len(GUARANTEES)} guarantees. Every one of them has a fail control "',
        '        f"That is 2 guarantees. Every one of them has a fail control "  # PLANTED',
        "the published guarantee COUNT stops being derived and becomes a typed "
        "number, which is the shape that goes stale silently: the document keeps "
        "agreeing with itself while the registry moves underneath it",
    ),
    "C2/pins": (
        "tests/test_contract_is_generated.py",
        "scripts/generate_contract.py",
        '            rows.append(f"| `{match.group(1)}` | `{match.group(3)}` |")',
        source(
            "            typed = '253249b5eb52770ec14d026f04f2c39749b75530'  # PLANTED",
            '            rows.append(f"| `{match.group(1)}` | `{typed}` |")',
        ),
        "the pinned commit in the contract stops being read from pyproject.toml and "
        "becomes a typed string, so the pin can move under a document that still "
        "names the old one",
    ),
    # -- C3: the command lines are the only door, and there is no database --
    "C3/import": (
        "tests/test_c3_the_command_lines_are_the_only_door.py",
        "sync.py",
        "from pass_billing_connector import doors\n",
        "from pass_billing_connector import doors\nimport monthly_billing  # noqa: PLANTED\n",
        "the runtime package imports monthly-billing's package: the connector "
        "stops being the same door everyone else uses and could reach the store "
        "past the command line",
    ),
    "C3/environment": (
        "tests/test_c3_the_command_lines_are_the_only_door.py",
        "doors.py",
        "    return subprocess.run(argv, capture_output=True, text=True, check=False)",
        source(
            '    __import__("os").environ.get("MONTHLY_BILLING_DSN")  # PLANTED',
            "    return subprocess.run(argv, capture_output=True, text=True, check=False)",
        ),
        "the connector reads a DSN from the environment: the first step toward a "
        "connection of its own, which A1.6 forbids by name",
    ),
    "C3/driver": (
        "tests/test_c3_the_command_lines_are_the_only_door.py",
        "pyproject.toml",
        "dependencies = []",
        'dependencies = ["psycopg[binary]>=3.1"]  # PLANTED',
        "a database driver arrives in the RUNTIME dependency list, which is the "
        "connector growing a database",
    ),
    "C3/scripts": (
        "tests/test_c3_the_command_lines_are_the_only_door.py",
        "doors.py",
        "    missing = [name for name in SCRIPTS if shutil.which(name) is None]",
        "    missing = []  # PLANTED: an absent script is not noticed",
        "a console script missing from PATH is no longer refused by name before "
        "the links are read; the first link would meet it as a subprocess error",
    ),
    "C3/pin": (
        "tests/test_c3_the_command_lines_are_the_only_door.py",
        "pyproject.toml",
        "garage-pass@253249b5eb52770ec14d026f04f2c39749b75530",
        "garage-pass@0000000000000000000000000000000000000000",
        "pyproject.toml pins a commit the installed package is not: the suite "
        "would then measure one commit and the contract name another",
    ),
    # -- C4: links are stated, never inferred --
    "C4/unknown-key": (
        "tests/test_c4_links_are_stated_never_inferred.py",
        "links.py",
        "    if unknown:",
        "    if False and unknown:  # PLANTED: an unknown key is ignored",
        "a key the connector does not read is accepted rather than refused, so a "
        "typo in a link's key names a link nobody meant",
    ),
    "C4/duplicate": (
        "tests/test_c4_links_are_stated_never_inferred.py",
        "links.py",
        "        if pass_key in seen_passes:",
        "        if False:  # PLANTED: a pass may appear in two links",
        "one pass in two links is accepted: two agreements' registers written "
        "from one pass, the single-writer rule broken by the document",
    ),
    "C4/case": (
        "tests/test_c4_links_are_stated_never_inferred.py",
        "links.py",
        "    return str(UUID(tenant))",
        "    return tenant  # PLANTED: the tenant compared as typed",
        "two links to one agreement whose tenant differs only in letter case are "
        "accepted, though both modules read it as one tenant: each run, one link "
        "releases the other pass's cars from billing",
    ),
    # -- C5: one verb, the instant, the day, the exits --
    "C5/naive": (
        "tests/test_c5_one_verb_the_instant_and_the_exits.py",
        "sync.py",
        "    if instant.tzinfo is None or instant.utcoffset() is None:",
        "    if False:  # PLANTED: a naive instant is accepted",
        "an instant with no offset is accepted, and billing's --at is handed a "
        "naive instant whose meaning depends on the machine",
    ),
    "C5/day": (
        "tests/test_c5_one_verb_the_instant_and_the_exits.py",
        "sync.py",
        "    return instant.date()",
        "    return (instant - instant.utcoffset()).date()  # PLANTED: the UTC day",
        "the day compared with garage-pass's days becomes the UTC day, not the "
        "day as written: a registration effective on the caller's tomorrow is "
        "registered tonight in a western zone",
    ),
    "C5/exit": (
        "tests/test_c5_one_verb_the_instant_and_the_exits.py",
        "cli.py",
        "    return EXIT_CONVERGED if report.converged else EXIT_DIVERGED",
        "    return EXIT_CONVERGED  # PLANTED: a divergence exits 0",
        "a run with a divergence exits 0: the loud failure the module exists to "
        "raise becomes a green exit an operator's script never looks past",
    ),
    # -- C6: the live register on the day --
    "C6/end-day": (
        "tests/test_c6_the_live_register_on_the_day.py",
        "live.py",
        "    return end is None or day < end",
        "    return end is None or day <= end  # PLANTED: free from the day AFTER",
        "a registration ending today is still live today: the identity garage-pass "
        "freed from today stays in billing one day longer",
    ),
    "C6/state": (
        "tests/test_c6_the_live_register_on_the_day.py",
        "live.py",
        "    if shown.get(\"state\") != STATE_ACTIVE:",
        "    if False:  # PLANTED: every state covers the day",
        "a suspended or revoked pass keeps its cars in billing's register",
    ),
    "C6/exit-only": (
        "tests/test_c6_the_live_register_on_the_day.py",
        "live.py",
        '                and row["vehicle_identity"] not in replaced):',
        "                and True):  # PLANTED: a replaced car stays live",
        "a car garage-pass has replaced on the pass stays in billing's register, "
        "covered at an entry and at an exit, beside the car that replaced it",
    ),
    # -- C7: registers first, releases by stored form --
    "C7/reimplementation": (
        "tests/test_c7_registers_first_releases_by_form.py",
        "sync.py",
        "def _text(value: object) -> str:",
        source(
            "def _fold(identity: str) -> str:  # PLANTED: billing's rule, copied",
            '    return "".join(c for c in identity.lower() if c.isalnum())',
            "",
            "",
            "def _text(value: object) -> str:",
        ),
        "a copy of billing's folded rule sits in the package: the day billing "
        "changes its rule the connector releases by a form billing never stored",
    ),
    "C7/fan-out": (
        "tests/test_c7_registers_first_releases_by_form.py",
        "doors.py",
        '                 agreement, "--vehicle", form, "--garage", garage])',
        '                 agreement, "--vehicle", form])  # PLANTED: the unnamed release',
        "the release no longer names its garage: the door fans out by identity "
        "over every covered garage, a stale exact-rule form takes the live "
        "folded-rule row that spells the same, and billing answers NOT COVERED "
        "for the new car at that garage -- the fan-out measured at the pinned commit",
    ),
    "C7/no-release": (
        "tests/test_c7_registers_first_releases_by_form.py",
        "sync.py",
        "    for garage, form in sorted(stale):",
        "    for garage, form in ():  # PLANTED: nothing stale is ever released",
        "no stale row is ever released: a foreign row and an ended car stay in "
        "billing forever, and the register only ever grows",
    ),
    # -- C8: a collision releases nothing --
    "C8": (
        "tests/test_c8_a_collision_releases_nothing.py",
        "sync.py",
        "    collisions = {key: ids for key, ids in forms.items() if len(ids) > 1}",
        "    collisions = {}  # PLANTED: two identities in one form is not noticed",
        "two live identities with one stored form are not a collision: the run "
        "releases as if they were two rows, and exits 0",
    ),
    # -- C9: the verdict is the final read --
    "C9/verdict": (
        "tests/test_c9_the_verdict_is_the_final_read.py",
        "sync.py",
        source(
            "    converged = (billing == expected and not collisions and not unknown",
            "                 and not final_refusals and not asymmetric)",
        ),
        source(
            "    converged = (  # PLANTED: the verdict from the calls, not the read",
            "        all(a.outcome == OUTCOME_DONE for a in actions) and not collisions",
            "        and not final_refusals and not asymmetric",
            "    )",
        ),
        "the verdict is taken from the door's answers rather than the final read: "
        "a run whose every call said done is reported converged whatever billing "
        "actually holds",
    ),
    "C9/unparseable": (
        "tests/test_c9_the_verdict_is_the_final_read.py",
        "doors.py",
        "            return Answer(OUTCOME_UNPARSEABLE, {}, _printed(done))",
        "            return Answer(OUTCOME_FAILED, {}, _printed(done))  # PLANTED",
        "a door that exited 0 with lines the connector cannot read is reported "
        "under the outcome published for a non-zero exit: the report's word and "
        "what happened disagree",
    ),
    "C9/unanswered": (
        "tests/test_c9_the_verdict_is_the_final_read.py",
        "sync.py",
        "    if not collisions and not unanswered:",
        "    if not collisions:  # PLANTED: an unanswered register does not stop the releases",
        "a live identity whose register the door did not answer has no known forms, "
        "so every row billing already holds for it looks stale and is released: one "
        "transient door failure uncovers a held car at every garage -- the C1 gate's "
        "blocker, measured before the rule existed",
    ),
    "C9/unknown-row": (
        "tests/test_c9_the_verdict_is_the_final_read.py",
        "sync.py",
        source(
            "    if not unknown:",
            '        return "the pass\'s live register stores nothing in that form there."',
        ),
        source(
            "    if True:  # PLANTED: the row is called foreign whatever the run knows",
            '        return "the pass\'s live register stores nothing in that form there."',
        ),
        "a row billing holds beside an identity whose form the run never learned is "
        "reported as one the pass stores nothing in: the report states as fact what "
        "the run does not know, two lines under its own STORED_FORM_UNKNOWN -- the "
        "re-gate's finding at 285fd80",
    ),
    "C9/final-refusals": (
        "tests/test_c9_the_verdict_is_the_final_read.py",
        "sync.py",
        "    final_refusals = _link_refusals(final_shown, final_register)",
        "    final_refusals = []  # PLANTED: the refusals are not checked on the final read",
        "a covered set or a registrar that moved under the run is not re-checked on "
        "the final read: the link is reported converged, exit 0, with 'equal' undefined",
    ),
    "C9/final-read": (
        "tests/test_c9_the_verdict_is_the_final_read.py",
        "sync.py",
        "    final_shown, final_replaced, final_register, read_findings = _read_both(link)",
        source(
            "    final_shown, final_replaced, final_register, read_findings = (  # PLANTED",
            "        shown, replaced, register, [])",
        ),
        "the final read is the first read: billing's rows before the writes are "
        "compared with the expectation, so every run that wrote anything diverges",
    ),
    "C9/rerun": (
        "tests/test_c9_the_verdict_is_the_final_read.py",
        "sync.py",
        "        if _register_refused(reports[index]) and any(",
        "        if False and any(  # PLANTED: a held link is never run again",
        "a car moving between two linked passes holds up the receiving link: its "
        "register is refused while the other link still holds the car, nothing is "
        "released for it, and its ended cars stay in billing until the next run",
    ),
    "C9/rerun-chain": (
        "tests/test_c9_the_verdict_is_the_final_read.py",
        "sync.py",
        "            ran.append((index, _released(again)))",
        "            pass  # PLANTED: a second attempt's releases are not tracked",
        "a chain is not followed: a link waiting on a car that only another link's "
        "SECOND attempt lets go is never run again, so that car is in no agreement's "
        "billing until the next run",
    ),
    "C9/later-read-words": (
        "tests/test_c9_the_verdict_is_the_final_read.py",
        "findings.py",
        "_A_LATER_READ = (",
        source(
            '_A_LATER_READ = "Nothing was written for this link."  # PLANTED',
            "_PLANTED_UNUSED = (",
        ),
        "the published sentence of a read that did not answer says nothing was written "
        "for the link, while the report beside it lists the writes the run already made "
        "before that read (billing's read before the releases, the final read, a second "
        "attempt's read), and they stand in billing",
    ),
    "C9/later-refusal-words": (
        "tests/test_c9_the_verdict_is_the_final_read.py",
        "findings.py",
        "_A_LATER_REFUSAL = (",
        source(
            '_A_LATER_REFUSAL = "Refused before any write."  # PLANTED',
            "_PLANTED_UNUSED = (",
        ),
        "the published sentence of one of step 1's refusals says the link was refused "
        "before any write, while the same refusal found on the final read or a second "
        "attempt's read stands beside writes the run already made",
    ),
    "C9/rerun-refused": (
        "tests/test_c9_the_verdict_is_the_final_read.py",
        "sync.py",
        "    if again.refused:",
        "    if False:  # PLANTED: a refused second attempt replaces the first",
        "a second attempt refused at its read replaces the first attempt's report: "
        "the link reads `refused`, which publishes that nothing was written, beside "
        "the first attempt's registers that were done and stand in billing",
    ),
    "C9/second-attempt-words": (
        "tests/test_c9_the_verdict_is_the_final_read.py",
        "findings.py",
        "        \"second attempt, where this finding stands if that attempt's register did not \"",
        "        \"second attempt, where this finding stands only if it was refused too, not \"",
        "the published STORED_FORM_UNKNOWN sentence says the finding stands on a second "
        "attempt only when its register was refused again, while the run names it for a "
        "`failed` or `unparseable` register too: the contract and the report disagree",
    ),
    "C9/final-replaced": (
        "tests/test_c9_the_verdict_is_the_final_read.py",
        "sync.py",
        "    final_live = live_register(final_shown, day, final_replaced)",
        "    final_live = live_register(final_shown, day, replaced)  # PLANTED",
        "the final read takes its replaced cars from the first read: a car garage-pass "
        "replaced under the run is still live on the final read, the pass is not named "
        "as changed, and the link converges with the replaced car in billing",
    ),
    # -- C10: convergence, not a journal --
    "C10": (
        "tests/test_c10_convergence_not_a_journal.py",
        "cli.py",
        "    print(report.rendered())",
        source(
            '    __import__("pathlib").Path("/dev/null").write_text(report.rendered())  # PLANTED',
            "    print(report.rendered())",
        ),
        "the connector writes a file: the first state of its own, which the next "
        "run could read instead of the two modules",
    ),
    # -- C11: refuse the link, writing nothing --
    "C11/registrar": (
        "tests/test_c11_refuse_the_link_writing_nothing.py",
        "sync.py",
        '    if register.get("registrar") != REGISTRAR_OUTSIDE:',
        "    if False:  # PLANTED: any registrar's register is written",
        "an agreement whose registrar is monthly-billing itself is written to "
        "through the door -- which the door refuses by name, so the link ends in "
        "refusals instead of one refusal before any write",
    ),
    "C11/sets": (
        "tests/test_c11_refuse_the_link_writing_nothing.py",
        "sync.py",
        "    if named != covered:",
        "    if False:  # PLANTED: garage sets need not agree",
        "a pass over two garages linked to an agreement covering one is written "
        "to as if the sets matched",
    ),
    "C11/ambiguous": (
        "tests/test_c11_refuse_the_link_writing_nothing.py",
        "sync.py",
        "    for shorter, longer in doors.ambiguous_garage_ids(tuple(sorted(covered))):",
        "    for shorter, longer in ():  # PLANTED: an ambiguous covered set is written to",
        "a covered set of `g` and `g: 2` is written to: the door's line for one "
        "garage reads as the other's, and a release's answer is attributed by a "
        "guess",
    ),
    "C11/garage-register": (
        "tests/test_c11_refuse_the_link_writing_nothing.py",
        "sync.py",
        source(
            "        findings.append(Finding(codes_read.finding, codes_read.detail))",
            "        return None, frozenset()",
        ),
        source(
            "        findings.append(Finding(codes_read.finding, codes_read.detail))",
            "        return pass_read.document, frozenset()  # PLANTED: no car replaced",
        ),
        "a garage register that did not answer is read as a pass on which no car was "
        "replaced: the link is written to, and a replaced car is registered again "
        "(on any read error)",
    ),
    # -- C12: the report's shape is published --
    "C12/code": (
        "tests/test_c12_the_report_shape_is_published.py",
        "sync.py",
        "            FINDING_DIVERGENCE, f\"billing holds {form!r} at {garage!r};",
        "            \"NOBODY_PUBLISHED_THIS\", f\"billing holds {form!r} at {garage!r};",
        "a finding code nobody registered is emitted: the contract lists what a "
        "reader can expect, and this is not on it",
    ),
    "C12/key": (
        "tests/test_contract_is_generated.py",
        "report.py",
        "    side: str | None = None\n",
        "    side: str | None = None\n    extra: str | None = None  # PLANTED\n",
        "a key the contract does not list arrives on every finding: the published "
        "shape and the rendered one disagree",
    ),
    # -- C13: the door's printed line is pinned --
    "C13/line": (
        "tests/test_c13_the_doors_printed_line_is_pinned.py",
        "doors.py",
        'STORED_FORM_LINE = "  at garage {garage}: {form}"',
        'STORED_FORM_LINE = "  at garage {garage} = {form}"  # PLANTED',
        "the pinned line no longer matches what the door prints: every door "
        "answer is unparseable and no form is ever known",
    ),
    "C13/ambiguous": (
        "tests/test_c13_the_doors_printed_line_is_pinned.py",
        "doors.py",
        "        if longer != shorter and longer.startswith(shorter + _LINE_SEPARATOR)",
        "        if False and longer.startswith(shorter + _LINE_SEPARATOR)  # PLANTED",
        "the parser names no covered set as ambiguous, so `g` and `g: 2` reach "
        "the longest-first order and a one-line answer is a guess",
    ),
    "C13/prefix": (
        "tests/test_c13_the_doors_printed_line_is_pinned.py",
        "doors.py",
        "    for garage in sorted(garages, key=len, reverse=True):",
        "    for garage in garages:  # PLANTED: a prefix claims the longer id's line",
        "a garage id that is a prefix of another claims the other's line, and "
        "the form read is the tail of the longer id plus the real form",
    ),
    # -- C14: nothing personal travels --
    "C14": (
        "tests/test_c14_nothing_personal_travels.py",
        "report.py",
        "    agreement_id: str\n    converged: bool",
        "    agreement_id: str\n    holder: str | None = None  # PLANTED\n    converged: bool",
        "a `holder` key arrives on every link report: the shape gains a personal "
        "field, and the key set is no longer closed to them",
    ),
    # -- C15: the exit guarantee --
    "C15": (
        "tests/test_c15_the_exit_guarantee.py",
        "doors.py",
        '    done = _run([MONTHLY_BILLING, "show-register", "--tenant", tenant,',
        '    done = _run([MONTHLY_BILLING, "record-payment", "--tenant", tenant,  # PLANTED',
        "the connector runs a verb that is not one of the five registration and "
        "read verbs: the claim that it touches registrations only is false",
    ),
    # -- C16: the fixture axis --
    "C16": (
        "tests/test_fixture_axes.py",
        "tests/harness.py",
        'GARAGE_B = ("garage-b", "Europe/Berlin", "exact")',
        'GARAGE_B = ("garage-b", "Europe/Berlin", "folded_alphanumeric")  # PLANTED',
        "the two fixture garages agree on identity rule, so every test of "
        "releasing by stored form samples one point on the axis that decides",
    ),
    # -- C17: the per-garage register is compared, or it is named --
    "C17": (
        "tests/test_c17_the_per_garage_register_is_named.py",
        "sync.py",
        "                 and not final_refusals and not asymmetric)",
        "                 and not final_refusals)  # PLANTED: an asymmetric pass converges",
        "an identity live at some of the pass's garages and not at others is named "
        "and still reported converged, exit 0: billing covers the car at a garage "
        "the pass does not, and nothing says so -- the outside round's N1",
    ),
}


def check_anchors() -> int:
    """Count every anchor. Zero or two is a dead control, and it is silent."""
    bad = 0
    for gid, (_target, path, anchor, _to, _why) in sorted(CONTROLS.items()):
        count = resolve(path).read_text().count(anchor)
        status = "ok" if count == 1 else "DEAD"
        if count != 1:
            bad += 1
        print(f"  {status:4}  {gid}  {path}  anchor appears {count}x")
    if bad:
        print(
            f"\n{bad} control(s) have no live anchor. An anchor that matches zero times "
            "plants nothing, and the control then reports green against unmodified "
            "source. Fix the anchors before trusting any result from this script."
        )
        return 1
    print(f"\nall {len(CONTROLS)} anchors live.")
    return 0


def _pytest(target: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", target, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


#: ``"0 passed" in stdout`` was the first form of this and it was WRONG:
#: "10 passed" contains it, so three live controls reported UNMEASURED and the run
#: said 14/17. A substring match confirms only that a substring was present -- the
#: rule this project already has, broken inside the machinery built to enforce it.
_NOTHING_RAN = re.compile(r"(?<!\d)0 passed|no tests ran|collected 0 items")


def run_control(gid: str) -> bool:
    target, path, anchor, replacement, why = CONTROLS[gid]
    print(f"\n=== {gid} — {GUARANTEES[guarantee_of(gid)]}")
    print(f"    plant: {path}")
    print(f"    breaks: {why}")

    green = _pytest(target)
    if green.returncode != 0:
        print(f"    UNMEASURED: {target} is already failing before anything was planted.")
        print(green.stdout[-1500:])
        return False
    if _NOTHING_RAN.search(green.stdout):
        print(f"    UNMEASURED: {target} ran no tests, so nothing here can go red.")
        print(green.stdout[-800:])
        return False

    with planted(path, anchor, replacement):
        red = _pytest(target)

    tail = [ln for ln in red.stdout.splitlines() if ln.startswith(("FAILED", "ERROR"))]
    summary = red.stdout.strip().splitlines()[-1] if red.stdout.strip() else ""
    if red.returncode == 0:
        print(f"    NOT A CONTROL: {target} stayed GREEN with its subject broken.")
        return False
    print(f"    RED, as required — {summary}")
    for line in tail[:6]:
        print(f"      {line}")
    return True


def main(argv: list[str]) -> int:
    if "--anchors" in argv:
        return check_anchors()

    named = [a for a in argv if not a.startswith("-")]
    wanted = [c for c in sorted(CONTROLS) if c in named or guarantee_of(c) in named]
    unknown = [
        a for a in named
        if a not in CONTROLS and a not in {guarantee_of(c) for c in CONTROLS}
    ]
    if unknown:
        print(f"no such control: {', '.join(unknown)}")
        return 2
    wanted = wanted or sorted(CONTROLS)

    missing = sorted(set(GUARANTEES) - {guarantee_of(c) for c in CONTROLS})
    if missing:
        print(
            f"registered guarantees with no fail-control: {', '.join(missing)}. "
            "Every guarantee is proven able to fail, or it is not a guarantee."
        )
        return 1

    if check_anchors():
        return 1

    results = {gid: run_control(gid) for gid in wanted}
    dead = [gid for gid, ok in results.items() if not ok]
    print(f"\n{len(results) - len(dead)}/{len(results)} controls fired.")
    if dead:
        print(f"DEAD CONTROLS: {', '.join(dead)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
