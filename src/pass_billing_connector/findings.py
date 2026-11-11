"""Every name the report can carry, and the sentence each one means.

**ONE REGISTRY, READ BY THE CONTRACT.** ``docs/CONTRACT.md`` renders these
tables from this file, and ``tests/test_c12_the_report_shape_is_published.py``
requires every code the connector emits to be listed here -- a finding nobody
published is refused by the test that scans the source for emitted codes.

A finding is a fact about one link on this run. On the link's first read, a
refusal (one of step 1's, or a read a module would not answer) stops the
connector before it writes anything for that link. The same finding on a later
read of the run stands beside the writes already made, which the link's actions
list. The rest are recorded and the final read decides.
"""

from __future__ import annotations

#: Step 1's refusals, by name. Each one names what differed.
FINDING_REGISTRAR_NOT_OUTSIDE = "REGISTRAR_NOT_OUTSIDE"
FINDING_GARAGE_SETS_DIFFER = "GARAGE_SETS_DIFFER"
FINDING_PASS_UNREADABLE = "PASS_UNREADABLE"
FINDING_PASS_GARAGE_UNREADABLE = "PASS_GARAGE_UNREADABLE"
FINDING_PASS_ROWS_OUTSIDE_ITS_GARAGES = "PASS_ROWS_OUTSIDE_ITS_GARAGES"
FINDING_REGISTER_ROWS_OUTSIDE_COVERED_SET = "REGISTER_ROWS_OUTSIDE_COVERED_SET"
FINDING_GARAGE_IDS_AMBIGUOUS = "GARAGE_IDS_AMBIGUOUS"
#: A module answered the READ with a refusal or a configuration sentence.
FINDING_GARAGE_PASS_REFUSED = "GARAGE_PASS_REFUSED"
FINDING_GARAGE_PASS_CONFIGURATION = "GARAGE_PASS_CONFIGURATION"
FINDING_MONTHLY_BILLING_REFUSED = "MONTHLY_BILLING_REFUSED"
FINDING_MONTHLY_BILLING_CONFIGURATION = "MONTHLY_BILLING_CONFIGURATION"
FINDING_GARAGE_PASS_UNPARSEABLE = "GARAGE_PASS_UNPARSEABLE"
FINDING_MONTHLY_BILLING_UNPARSEABLE = "MONTHLY_BILLING_UNPARSEABLE"
#: Recorded on the way; the final read decides.
FINDING_COLLISION = "COLLISION"
FINDING_STORED_FORM_UNKNOWN = "STORED_FORM_UNKNOWN"
FINDING_PASS_CHANGED_DURING_RUN = "PASS_CHANGED_DURING_RUN"
#: The verdict.
FINDING_DIVERGENCE = "DIVERGENCE"
FINDING_PASS_REGISTER_ASYMMETRIC = "PASS_REGISTER_ASYMMETRIC"

#: What one of step 1's refusals means for the link's writes, said once for all
#: of them: they are checked on the link's first read, again on the final read,
#: and on a second attempt's read.
_A_LATER_REFUSAL = (
    "On the link's first read it refuses the link before any write. On a later "
    "read of the run -- the final read, or a second attempt's read -- the writes "
    "already made stand, the link's actions list them, and the link does not "
    "converge."
)
#: What a read that did not answer means for the link's writes, said once for
#: every read finding that names a module.
_A_LATER_READ = (
    "When it is the link's first read, the link is refused and nothing was written "
    "for it. When it is a later read of the run -- the final read, a second "
    "attempt's read, or billing's read before the releases -- the writes already "
    "made stand, and the link's actions list them."
)

FINDINGS: dict[str, str] = {
    FINDING_REGISTRAR_NOT_OUTSIDE: (
        "The agreement's registrar is not `outside`, so its register is monthly "
        "billing's own to write, not the connector's. " + _A_LATER_REFUSAL
    ),
    FINDING_GARAGE_SETS_DIFFER: (
        "The garages the pass names and the garages the agreement covers are not "
        "the same set, compared as exact text. A link whose two sides disagree on "
        "WHERE has no register to make equal. The finding carries both sets. "
        + _A_LATER_REFUSAL
    ),
    FINDING_PASS_UNREADABLE: (
        "garage-pass holds the pass but cannot read it (`unreadable` on the read is "
        "not null), so its valid days are not known. The finding carries "
        "garage-pass's own refusal. " + _A_LATER_REFUSAL
    ),
    FINDING_PASS_GARAGE_UNREADABLE: (
        "A garage the pass names is stored unreadable in garage-pass "
        "(`unreadable_garages`). The finding names the garage and carries "
        "garage-pass's own refusal. " + _A_LATER_REFUSAL
    ),
    FINDING_PASS_ROWS_OUTSIDE_ITS_GARAGES: (
        "garage-pass shows a registration row at a garage the pass does not name "
        "(`garages_not_named`). The finding names the garages. " + _A_LATER_REFUSAL
    ),
    FINDING_REGISTER_ROWS_OUTSIDE_COVERED_SET: (
        "monthly billing shows a registration row at a garage the agreement's latest "
        "version does not cover (`garages_not_covered`). The finding names the "
        "garages. " + _A_LATER_REFUSAL
    ),
    FINDING_GARAGE_IDS_AMBIGUOUS: (
        "One covered garage's id is another covered garage's id plus the door's "
        "separator (`: `) plus anything -- `g` and `g: 2` -- so the door's printed "
        "line `  at garage {id}: {form}` has two readings and no parser can tell "
        "them apart. The finding names each such pair, and the parser is never "
        "asked the question. " + _A_LATER_REFUSAL
    ),
    FINDING_GARAGE_PASS_REFUSED: (
        "garage-pass refused the read by name (its exit 3): a wrong tenant, a garage "
        "the pass does not name, a pass it does not hold. The finding carries the "
        "module's own refusal code and detail. " + _A_LATER_READ
    ),
    FINDING_GARAGE_PASS_CONFIGURATION: (
        "garage-pass answered with a configuration sentence (its exit 2: no DSN, a "
        "database that did not connect). The finding carries the sentence. "
        + _A_LATER_READ
    ),
    FINDING_MONTHLY_BILLING_REFUSED: (
        "monthly-billing refused or could not find what the read named (its exit 2: "
        "REFUSED or NOT FOUND on stderr) -- a wrong tenant, an agreement it does not "
        "hold. The finding carries the module's own sentence. " + _A_LATER_READ
    ),
    FINDING_MONTHLY_BILLING_CONFIGURATION: (
        "monthly-billing exited with a status the connector does not read as a "
        "refusal (no DSN, a database that did not connect). The finding carries what "
        "it printed. " + _A_LATER_READ
    ),
    FINDING_GARAGE_PASS_UNPARSEABLE: (
        "garage-pass exited 0 but what it printed is not the JSON the connector "
        "reads. The finding carries the output. " + _A_LATER_READ
    ),
    FINDING_MONTHLY_BILLING_UNPARSEABLE: (
        "monthly-billing exited 0 but what it printed is not the JSON, or not the "
        "`  at garage {id}: {form}` lines, the connector reads. The finding carries "
        "the output."
    ),
    FINDING_COLLISION: (
        "Two live identities of the pass have ONE stored form at one garage under "
        "that garage's rule. Releasing either would take out the other, so NOTHING "
        "is released for this link and it does not converge. The finding names the "
        "garage, the form and both identities."
    ),
    FINDING_STORED_FORM_UNKNOWN: (
        "A live identity's registration did not come back `done` from the door "
        "(refused, failed, or an answer the connector cannot read), so its stored "
        "form at the covered garages is not known to this run. The finding names the "
        "identity and what the door said; the door's own words are on the action. "
        "NOTHING IS RELEASED for the link that run -- every row billing may already "
        "hold for that identity would look stale, and an incomplete picture of the "
        "desired set is never a licence to delete; the registers that did answer "
        "stand, and the next run re-reads. The link does not converge. Also raised "
        "on the final read for an identity live there that this run did not register. "
        "A `refused` register -- a car held by ANOTHER agreement -- is not transient: it "
        "stands until an operator moves the car, and until then the link releases "
        "nothing on every run, with this finding each time. That is the rule holding, "
        "not a fault of the connector's. When another link of the same run released a "
        "row after this link ran -- a car moving between two linked passes -- the link "
        "is run once more in that run, and the report takes its findings from the "
        "second attempt, where this finding stands if that attempt's register did not "
        "come back `done` either, or the identity is live only on that attempt's final "
        "read. A second attempt refused at its read writes nothing: the report is then "
        "the first attempt's, this finding included, with the second attempt's findings "
        "after it."
    ),
    FINDING_PASS_CHANGED_DURING_RUN: (
        "The final read of the pass shows a live register different from the one the "
        "run started from. The run wrote for the register it read first; the verdict "
        "is against the final one, so the link may not converge until the next run."
    ),
    FINDING_DIVERGENCE: (
        "After the run's writes, the final read of billing's register differs from "
        "the pass's live register: one (garage, form) that is on one side only. "
        "Exit 1. The finding names the garage, the form and which side holds it. A "
        "`billing_only` row while some live identity's stored form is unknown to the "
        "run (`STORED_FORM_UNKNOWN`) may be that identity's: the run cannot tell, so "
        "the finding's sentence says so, `identities` names whose forms are unknown, "
        "and the row is not called foreign."
    ),
    FINDING_PASS_REGISTER_ASYMMETRIC: (
        "On the final read the pass holds an identity live at SOME of its garages "
        "and not at others. Billing's door registers a car at every covered garage "
        "or at none, so that is a picture billing cannot be made to hold, and the "
        "connector's comparison is of the identity set: left unnamed it would "
        "converge while billing covered the car at a garage the pass does not. So "
        "it is named -- the identity, the garages that hold it, the garages that do "
        "not -- the link does not converge, exit 1. The finding is raised on the "
        "final read, after the run's own registers and releases, and causes no "
        "write of its own: the identity the first read showed live was registered "
        "at every covered garage in step 2, as every live identity is, and the "
        "next run makes the same register and names it again. Not reachable "
        "through garage-pass's own "
        "verbs at the pinned commit (a registration is written at every garage of "
        "the pass or none, and ended at every one); a row written past them is."
    ),
}

#: Which side of a divergence holds the row.
SIDE_BILLING_ONLY = "billing_only"
SIDE_PASS_ONLY = "pass_only"
SIDES: dict[str, str] = {
    SIDE_BILLING_ONLY: "billing holds a row at this garage in this form; no live identity "
    "whose stored form the run learned stores in it there",
    SIDE_PASS_ONLY: "the pass has a live identity storing in this form at this garage; "
    "billing holds no such row",
}

#: What an action can report.
ACTION_REGISTER = "register"
ACTION_RELEASE = "release"
ACTIONS: dict[str, str] = {
    ACTION_REGISTER: "`monthly-billing register-vehicle` for one live identity of the pass, "
    "as garage-pass recorded it, at the instant given",
    ACTION_RELEASE: "`monthly-billing release-vehicle --garage` for one stored form billing "
    "holds at ONE covered garage that no live identity stores in there; the action names "
    "the garage",
}
OUTCOME_DONE = "done"
OUTCOME_REFUSED = "refused"
OUTCOME_FAILED = "failed"
OUTCOME_UNPARSEABLE = "unparseable"
OUTCOMES: dict[str, str] = {
    OUTCOME_DONE: "the door answered, exit 0, in lines the connector reads; `stored` carries "
    "what it printed per garage",
    OUTCOME_REFUSED: "the door refused by name, exit 2; `detail` carries its sentence",
    OUTCOME_FAILED: "the door exited with a status that is neither 0 nor 2 (no DSN, a database "
    "that did not connect); `detail` carries what it printed",
    OUTCOME_UNPARSEABLE: "the door exited 0 but what it printed is not the `  at garage {id}: "
    "{form}` lines the connector reads, so nothing is known about what it did; `detail` "
    "carries what it printed and the final read decides",
}

#: Why a register action was made.
REASON_LIVE = "live on the day"
REASON_NOT_LIVE_FORM = "billing holds this form; no live identity stores in it"
REASONS: dict[str, str] = {
    REASON_LIVE: "the identity is in the pass's live register on the day",
    REASON_NOT_LIVE_FORM: "billing's register holds the form at this garage and no live "
    "identity of the pass stores in it there",
}

#: The connector's exit codes.
EXIT_CONVERGED = 0
EXIT_DIVERGED = 1
EXIT_CONFIGURATION = 2
EXITS: dict[int, str] = {
    EXIT_CONVERGED: "every link's billing register equals its pass's live register on the "
    "final read",
    EXIT_DIVERGED: "at least one link's does not -- a refusal, a collision, a divergence, or "
    "a module that would not answer. The report says which, per link",
    EXIT_CONFIGURATION: "the connector itself could not run: the links document is missing, "
    "not JSON, or not of the published shape; `--at` is not an ISO instant with an "
    "offset; a console script is not on PATH. A sentence on stderr, no report",
}
