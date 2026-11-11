"""One link, one run: registers first, releases by stored form, the verdict
from the final read.

THE ORDER, AND WHY.

1. **Read both, and refuse the link -- writing nothing -- on anything that
   makes "equal" undefined**: a registrar that is not `outside`, garage sets
   that differ, a pass or garage stored unreadable, rows outside either set,
   a covered set whose ids the door's printed line cannot tell apart (one id
   is another plus `: ` plus anything). Each refusal is a finding by name; a
   module that would not answer the read is a finding carrying the module's
   own words.

2. **Register every live identity** (``live.py``: a car garage-pass has
   replaced on the pass, its QR exit only, is not live), as garage-pass
   recorded it, through ``register-vehicle`` -- idempotent at the door: a row already this
   agreement's is left and its stored form still printed. The printed form
   per garage is COLLECTED, and it is the only source of a stored form the
   connector ever has. The connector never reimplements billing's
   normalisation; the door's answer is the whole of what it knows about forms.

3. **A collision stops the releases -- and so does a register the door did
   not answer.** Two live identities with one stored form at one garage (the
   folded rule makes `AB-123` and `ab123` one billing row): releasing either
   would take out the other, so nothing is released for the link, it does not
   converge, and the report names the garage, the form and both identities.
   And a live identity whose ``register-vehicle`` did not come back ``done``
   -- refused, failed, or an answer the connector cannot read -- has no known
   forms, so every row billing may already hold for it would look stale.
   The connector cannot tell "the car is not registered" from "the door did
   not tell me", and an incomplete picture of the desired set is never a
   licence to delete: nothing is released for the link that run, the
   registers that did answer stand, ``STORED_FORM_UNKNOWN`` names the identity
   and the door's words, the link does not converge, and the next run
   re-reads. (Measured before this rule existed: one transient failure on a
   held car's register released that car's rows at every garage.) A
   ``refused`` register -- the door's exit 2, a car held by ANOTHER
   agreement -- is not transient: it stands until an operator moves the car,
   and until then this link releases nothing on every run, loudly (exit 1,
   the finding, the identity, the door's words). That is this rule holding,
   not a fault of the connector's: it cannot tell a held car from a door that
   did not answer, and deletes nothing on either. The one exception is a car
   another link OF THE SAME RUN lets go -- a car moving between two linked
   passes: when another link released a row after this one ran, this link is
   run once more, from fresh reads, before the run ends (``sync``), and its
   report keeps both attempts' actions and takes its findings and verdict
   from the second -- unless the second attempt is refused at its read (a
   module that did not answer, or a refusal of step 1 that began between the
   attempts): it then wrote nothing, and the report is the first attempt's,
   not refused, with its actions and the second attempt's findings added.

4. **Release by stored form, never by raw identity, AT THE GARAGE THAT
   STORES IT.** Every row billing holds at a garage whose form is not among
   step 2's forms at that garage is released by passing that form back to
   ``release-vehicle --garage`` naming that garage. That relies on billing's
   normalisation being idempotent -- ``n(n(x)) == n(x)`` -- which was measured
   at the pinned commit over every code point under every rule before this
   was built, and which ``tests/test_c7_...`` measures again at the door.

   **AND THE GARAGE IS ALWAYS NAMED.** The door's unnamed release takes ONE
   identity and releases it at EVERY covered garage under each garage's own
   rule -- so releasing a stale exact-rule form `ab123` at garage B would also
   release the live folded-rule row `ab123` at garage A, which is `AB-123`'s,
   and the car would be uncovered at A until it was registered again.
   Measured at the pinned commit, not reasoned about. Naming the garage
   (billing's G46) takes the one row and no other, so no release of this
   connector's ever takes a live car's row, and there is no window to state.

5. **Read both again. The verdict is the final read.** Billing's rows, as
   (garage, form), against every live identity's forms from the door's
   answers. A difference either way is a DIVERGENCE, per garage, per form,
   naming the side that holds it; a live identity whose registration the
   door refused has no known form and cannot converge; a pass that changed
   under the run is named; an identity live at some of the pass's garages
   and not at others is named (``PASS_REGISTER_ASYMMETRIC``) and does not
   converge, because the door registers everywhere or nowhere and the
   identity-set comparison alone would call it equal. A row billing holds
   that no KNOWN form accounts for, while some live identity's form is
   unknown, may be that identity's:
   its sentence names the identities whose forms the run does not know and
   does not call the row foreign -- the report claims nothing the run could
   not learn. **And step 1's refusals are checked again against
   the final reads**: a registrar, a garage set, an unreadable record, a row
   outside a set or an ambiguous id that changed under the run is named
   exactly as it would be at the start of a run, and the link does not
   converge -- "equal" that became undefined during the run is not called
   equal at its end. Every register and release the run made is in the
   report with its reason and the door's own words.

THE CROSS-DATABASE FAILURE STATE IS CONVERGENCE. The two writes are never one
transaction. Nothing here survives between runs, so a run killed half-way is
repaired by the next run from fresh reads, and no state of the connector's
can go stale. Two runs over one link at once are NOT serialised by the
connector; the operator runs one at a time per link, and a run whose final
read disagrees exits 1.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import date, datetime

from pass_billing_connector import doors
from pass_billing_connector.findings import (
    ACTION_REGISTER,
    ACTION_RELEASE,
    FINDING_COLLISION,
    FINDING_DIVERGENCE,
    FINDING_GARAGE_IDS_AMBIGUOUS,
    FINDING_GARAGE_SETS_DIFFER,
    FINDING_PASS_CHANGED_DURING_RUN,
    FINDING_PASS_GARAGE_UNREADABLE,
    FINDING_PASS_REGISTER_ASYMMETRIC,
    FINDING_PASS_ROWS_OUTSIDE_ITS_GARAGES,
    FINDING_PASS_UNREADABLE,
    FINDING_REGISTER_ROWS_OUTSIDE_COVERED_SET,
    FINDING_REGISTRAR_NOT_OUTSIDE,
    FINDING_STORED_FORM_UNKNOWN,
    OUTCOME_DONE,
    OUTCOME_REFUSED,
    REASON_LIVE,
    REASON_NOT_LIVE_FORM,
    SIDE_BILLING_ONLY,
    SIDE_PASS_ONLY,
)
from pass_billing_connector.links import Link
from pass_billing_connector.live import LiveRegister, exit_only_identities, live_register
from pass_billing_connector.report import Action, Finding, LinkReport, Report, Row

REGISTRAR_OUTSIDE = "outside"


class InstantRefused(Exception):
    """``--at`` is not an ISO instant with an offset. A sentence, exit 2."""


def day_of(at: str) -> date:
    """THE DATE OF THE INSTANT AS WRITTEN -- garage-pass's own convention for
    ``effective_day`` ("the caller's one day at every garage"). Not converted
    to any garage's zone: a pass spans garages in different zones and which
    day is the caller's call, made by writing the instant."""
    try:
        instant = datetime.fromisoformat(at)
    except ValueError:
        raise InstantRefused(f"--at {at!r} is not an ISO instant.") from None
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise InstantRefused(f"--at {at!r} carries no offset; the instant is stated with one.")
    return instant.date()


def sync(links: tuple[Link, ...], at: str) -> Report:
    day = day_of(at)
    reports = [sync_link(link, at, day) for link in links]
    # A CAR MOVING BETWEEN TWO LINKED PASSES. The receiving link's register is
    # refused while the giving link's agreement still holds the car, so the
    # receiving link releases nothing -- and the giving link, later in the
    # file, then lets the car go. Such a link is run ONCE MORE, from fresh
    # reads, when another link released a row after it ran: the car is
    # registered and this link's releases are made in the same run, instead of
    # its ended cars staying in billing until the next one. In run order:
    # (link, whether that run released a row).
    ran = [(index, _released(report)) for index, report in enumerate(reports)]
    for index, link in enumerate(links):
        if _register_refused(reports[index]) and any(
            released for other, released in ran[index + 1:] if other != index
        ):
            again = sync_link(link, at, day)
            reports[index] = _both_attempts(reports[index], again)
            ran.append((index, _released(again)))
    return Report(at=at, day=day.isoformat(), converged=all(r.converged for r in reports),
                  links=tuple(reports))


def _both_attempts(first: LinkReport, again: LinkReport) -> LinkReport:
    """One report for a link run twice. When the second attempt read and
    judged, the report keeps both attempts' actions and takes its findings and
    verdict from the second. When the second attempt was REFUSED at its read
    -- a module that did not answer, or a refusal of step 1 that began between
    the attempts -- that attempt wrote nothing, and what the first attempt
    wrote stands: the report is the first attempt's (not refused; its actions,
    live register, expected and billing rows), with the second attempt's
    findings after its own, and the link does not converge. A refused report
    carries no action, so it is never the base of one that does."""
    if again.refused:
        return replace(first, converged=False, findings=first.findings + again.findings)
    return replace(again, actions=first.actions + again.actions)


def _register_refused(report: LinkReport) -> bool:
    return any(a.action == ACTION_REGISTER and a.outcome == OUTCOME_REFUSED
               for a in report.actions)


def _released(report: LinkReport) -> bool:
    return any(a.action == ACTION_RELEASE and a.outcome == OUTCOME_DONE for a in report.actions)


def _refused(link: Link, findings: list[Finding]) -> LinkReport:
    return LinkReport(
        pass_tenant=link.pass_tenant, pass_id=link.pass_id, pass_garage=link.pass_garage,
        billing_tenant=link.billing_tenant, agreement_id=link.agreement_id,
        converged=False, refused=True, live={}, expected=(), billing=(), actions=(),
        findings=tuple(findings),
    )


def _read_both(link: Link) -> tuple[dict | None, frozenset[str], dict | None, list[Finding]]:
    findings: list[Finding] = []
    shown, replaced = _read_pass(link, findings)
    register_read = doors.show_register(link.billing_tenant, link.agreement_id)
    if not register_read.ok:
        findings.append(Finding(register_read.finding, register_read.detail))
    return shown, replaced, register_read.document, findings


def _read_pass(link: Link, findings: list[Finding]) -> tuple[dict | None, frozenset[str]]:
    """The pass as ``show-pass`` printed it, and the cars garage-pass has
    replaced on it, from the garage's register (``live.py``). Without the
    second read the pass has no live register, so a garage register that would
    not answer stands in for the pass read, carrying garage-pass's words."""
    pass_read = doors.show_pass(link.pass_tenant, link.pass_garage, link.pass_id)
    if not pass_read.ok:
        findings.append(Finding(pass_read.finding, pass_read.detail))
        return None, frozenset()
    codes_read = doors.show_garage_register(link.pass_tenant, link.pass_garage)
    if not codes_read.ok:
        findings.append(Finding(codes_read.finding, codes_read.detail))
        return None, frozenset()
    return pass_read.document, exit_only_identities(codes_read.document, link.pass_id)


def _link_refusals(shown: dict, register: dict) -> list[Finding]:
    """K5.1: what makes "equal" undefined for this link, each by name."""
    findings: list[Finding] = []
    if register.get("registrar") != REGISTRAR_OUTSIDE:
        findings.append(Finding(
            FINDING_REGISTRAR_NOT_OUTSIDE,
            f"agreement {register.get('agreement')!r} states registrar "
            f"{register.get('registrar')!r}; the connector writes only an `outside` register.",
        ))
    named = set(shown.get("garages") or ())
    covered = set(register.get("covered_garages") or ())
    if named != covered:
        findings.append(Finding(
            FINDING_GARAGE_SETS_DIFFER,
            f"the pass names {sorted(named)}; the agreement covers {sorted(covered)}.",
        ))
    if shown.get("unreadable") is not None:
        findings.append(Finding(FINDING_PASS_UNREADABLE, _text(shown["unreadable"])))
    for garage, refusal in sorted((shown.get("unreadable_garages") or {}).items()):
        findings.append(Finding(FINDING_PASS_GARAGE_UNREADABLE, _text(refusal), garage=garage))
    not_named = list(shown.get("garages_not_named") or ())
    if not_named:
        findings.append(Finding(
            FINDING_PASS_ROWS_OUTSIDE_ITS_GARAGES,
            f"garage-pass shows rows at {sorted(not_named)}, which the pass does not name.",
        ))
    not_covered = list(register.get("garages_not_covered") or ())
    if not_covered:
        findings.append(Finding(
            FINDING_REGISTER_ROWS_OUTSIDE_COVERED_SET,
            f"billing shows rows at {sorted(not_covered)}, which the latest version does not "
            "cover.",
        ))
    for shorter, longer in doors.ambiguous_garage_ids(tuple(sorted(covered))):
        findings.append(Finding(
            FINDING_GARAGE_IDS_AMBIGUOUS,
            f"covered garage {longer!r} is {shorter!r} plus the door's separator plus text, so "
            f"a line the door prints for {shorter!r} can read as one for {longer!r}.",
            garage=longer,
        ))
    return findings


def _text(value: object) -> str:
    import json

    return value if isinstance(value, str) else json.dumps(value, sort_keys=True)


def sync_link(link: Link, at: str, day: date) -> LinkReport:
    shown, replaced, register, findings = _read_both(link)
    if shown is None or register is None:
        return _refused(link, findings)
    findings = _link_refusals(shown, register)
    if findings:
        return _refused(link, findings)

    garages = tuple(sorted(register["covered_garages"]))
    actions: list[Action] = []
    first_live = live_register(shown, day, replaced)

    # 2. Registers, collecting the door's forms. forms[(garage, form)] is the
    #    set of live identities the door stored in that form there.
    identity_forms: dict[str, dict[str, str]] = {}
    forms: dict[tuple[str, str], set[str]] = defaultdict(set)
    for identity in first_live.identities():
        _register(link, identity, at, garages, REASON_LIVE, actions, identity_forms, forms,
                  findings)

    # 3. A collision stops the releases; so does a register the door did not
    #    answer `done` -- its rows are unknown, not stale.
    collisions = {key: ids for key, ids in forms.items() if len(ids) > 1}
    unanswered = [a.identity for a in actions if a.action == "register"
                  and a.outcome != OUTCOME_DONE]
    for (garage, form), identities in sorted(collisions.items()):
        findings.append(Finding(
            FINDING_COLLISION,
            f"identities {sorted(identities)} both store as {form!r} at {garage!r}; nothing "
            "is released for this link.",
            garage=garage, form=form, identities=tuple(sorted(identities)),
        ))

    # 4. Releases by stored form, each at the one garage that stores it.
    if not collisions and not unanswered:
        _release_stale(link, garages, actions, forms, findings)

    # 5. The final read decides.
    final_shown, final_replaced, final_register, read_findings = _read_both(link)
    findings.extend(read_findings)
    if final_shown is None or final_register is None:
        return LinkReport(
            pass_tenant=link.pass_tenant, pass_id=link.pass_id, pass_garage=link.pass_garage,
            billing_tenant=link.billing_tenant, agreement_id=link.agreement_id,
            converged=False, refused=False, live=dict(first_live.by_garage), expected=(),
            billing=(), actions=tuple(actions), findings=tuple(findings),
        )
    # Step 1's refusals, against the final reads: what made "equal" defined
    # at the start must still hold at the end.
    final_refusals = _link_refusals(final_shown, final_register)
    findings.extend(final_refusals)
    final_live = live_register(final_shown, day, final_replaced)
    if final_live.pairs() != first_live.pairs():
        findings.append(Finding(
            FINDING_PASS_CHANGED_DURING_RUN,
            f"the run started from {_pairs(first_live)} and the final read shows "
            f"{_pairs(final_live)}.",
        ))
    # The pass's register is compared per garage, or it is named: an identity
    # live at some of the pass's garages and not at others is a picture the
    # door cannot be made to hold (it registers everywhere or nowhere), and the
    # identity-set comparison below would call it converged. Named from the
    # final read; it licenses no register and no release.
    asymmetric = _asymmetric(final_live, findings)
    expected: set[tuple[str, str]] = set()
    for identity in final_live.identities():
        stored = identity_forms.get(identity)
        if stored is None:
            if not any(f.code == FINDING_STORED_FORM_UNKNOWN and f.identity == identity
                       for f in findings):
                findings.append(Finding(
                    FINDING_STORED_FORM_UNKNOWN,
                    f"identity {identity!r} is live on the final read and was not registered "
                    "by this run, so its stored form is not known.",
                    identity=identity,
                ))
            continue
        expected |= {(g, f) for g, f in stored.items()}
    billing = {(row["garage"], row["identity_normalised"])
               for row in final_register.get("registrations") or ()}
    # The identities whose stored forms this run never learned. A row billing
    # holds that no KNOWN form accounts for may be one of theirs, and the
    # sentence on it says so rather than calling the row foreign.
    unknown = tuple(sorted({f.identity for f in findings
                            if f.code == FINDING_STORED_FORM_UNKNOWN and f.identity}))
    for garage, form in sorted(billing - expected):
        findings.append(Finding(
            FINDING_DIVERGENCE, f"billing holds {form!r} at {garage!r}; "
            + _billing_only_tail(unknown), garage=garage, form=form, side=SIDE_BILLING_ONLY,
            identities=unknown,
        ))
    for garage, form in sorted(expected - billing):
        findings.append(Finding(
            FINDING_DIVERGENCE, f"the pass's live register stores {form!r} at {garage!r}; "
            "billing holds no such row.", garage=garage, form=form, side=SIDE_PASS_ONLY,
        ))
    converged = (billing == expected and not collisions and not unknown
                 and not final_refusals and not asymmetric)
    return LinkReport(
        pass_tenant=link.pass_tenant, pass_id=link.pass_id, pass_garage=link.pass_garage,
        billing_tenant=link.billing_tenant, agreement_id=link.agreement_id,
        converged=converged, refused=False, live=dict(final_live.by_garage),
        expected=tuple(Row(g, f) for g, f in sorted(expected)),
        billing=tuple(Row(g, f) for g, f in sorted(billing)),
        actions=tuple(actions), findings=tuple(findings),
    )


def _asymmetric(live: LiveRegister, findings: list[Finding]) -> list[Finding]:
    """One finding per identity live at a strict subset of the pass's garages,
    appended to ``findings`` and returned."""
    named: list[Finding] = []
    for identity in live.identities():
        holds = sorted(g for g, ids in live.by_garage.items() if identity in ids)
        lacks = sorted(g for g in live.by_garage if g not in holds)
        if holds and lacks:
            named.append(Finding(
                FINDING_PASS_REGISTER_ASYMMETRIC,
                f"identity {identity!r} is live at {holds} and not at {lacks}; billing's door "
                "registers at every covered garage or none, so this register cannot be made "
                "equal and the link does not converge.",
                identity=identity,
            ))
    findings.extend(named)
    return named


def _pairs(live: LiveRegister) -> list[list[str]]:
    return [list(p) for p in sorted(live.pairs())]


def _billing_only_tail(unknown: tuple[str, ...]) -> str:
    """The rest of a `billing_only` sentence, chosen by what the run knows.

    `expected` is built from the forms the door answered, so when every live
    identity's register came back `done` a row outside it is one no live
    identity stores in -- and the sentence says so. When a live identity's
    stored form is NOT known to the run (`STORED_FORM_UNKNOWN`: a register the
    door did not answer, or an identity live only on the final read), the run
    cannot tell that identity's rows from stale ones -- it never reimplements
    billing's normalisation -- so the sentence names the identities whose
    forms it does not know and claims nothing about whose the row is.
    (Measured before this sentence existed: a held car's own rows, kept by
    the rule above, were reported as rows the pass stores nothing in.)
    """
    if not unknown:
        return "the pass's live register stores nothing in that form there."
    return (
        "no live identity whose stored form this run learned stores in it there, and the "
        f"stored forms of {list(unknown)} are not known to this run, so whether this row is "
        "theirs is not known."
    )


def _register(link: Link, identity: str, at: str, garages: tuple[str, ...], reason: str,
              actions: list[Action], identity_forms: dict[str, dict[str, str]],
              forms: dict[tuple[str, str], set[str]], findings: list[Finding]) -> None:
    answer = doors.register_vehicle(link.billing_tenant, link.agreement_id, identity, at, garages)
    actions.append(Action(
        action="register", outcome=answer.outcome, reason=reason, identity=identity,
        stored=dict(answer.stored), detail=answer.reason,
    ))
    if answer.outcome != OUTCOME_DONE:
        if reason == REASON_LIVE:
            findings.append(Finding(
                FINDING_STORED_FORM_UNKNOWN,
                f"the door did not register {identity!r} ({answer.outcome}): {answer.reason}; "
                "its stored forms are not known, so nothing is released for this link.",
                identity=identity,
            ))
        return
    identity_forms[identity] = dict(answer.stored)
    for garage, form in answer.stored.items():
        forms[(garage, form)].add(identity)


def _release_stale(link: Link, garages: tuple[str, ...], actions: list[Action],
                   forms: dict[tuple[str, str], set[str]], findings: list[Finding]) -> None:
    mid = doors.show_register(link.billing_tenant, link.agreement_id)
    if not mid.ok:
        findings.append(Finding(mid.finding, mid.detail))
        return
    held = {(row["garage"], row["identity_normalised"])
            for row in mid.document.get("registrations") or ()}
    # The stale rows, as (garage, form), each released at ITS garage by ITS
    # form: one row per door call, and the door's answer is that one row. A
    # row whose form another garage's live car also stores in is no different
    # -- the release named the garage, so the other garage's row is not
    # reached. The final read decides what was taken.
    stale = {(garage, form) for (garage, form) in held if (garage, form) not in forms}
    for garage, form in sorted(stale):
        answer = doors.release_vehicle(link.billing_tenant, link.agreement_id, form, garage,
                                       garages)
        actions.append(Action(
            action="release", outcome=answer.outcome, reason=REASON_NOT_LIVE_FORM, form=form,
            garage=garage, stored=dict(answer.stored), detail=answer.reason,
        ))
