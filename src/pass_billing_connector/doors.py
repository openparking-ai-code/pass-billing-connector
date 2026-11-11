"""The two command lines, and nothing else.

**THIS IS THE WHOLE OF THE CONNECTOR'S CONTACT WITH EITHER MODULE.** Every read
and every write goes through ``garage-pass`` or ``monthly-billing`` run as a
subprocess, with the environment the operator gave the connector passed through
untouched -- the modules read their own DSNs (``GARAGE_PASS_DSN``,
``MONTHLY_BILLING_DSN``) from it; the connector never does. It imports neither
package, opens no connection, and holds no DSN. Each module keeps its own
transaction boundary and its own row security, and the connector is "the same
door everyone else uses". ``tests/test_c3_...`` enforces that from the source
with a planted import as its control, not from this docstring.

**WHAT IS READ FROM EACH MODULE, PINNED.** Measured at the commits
``pyproject.toml`` pins, and re-measured by the tests against those commits so
a change there reddens this repository's CI rather than silently mis-parsing:

garage-pass (``show-pass --tenant T --garage G --pass-id P``)
  exit 0, JSON on stdout: ``pass``, ``state``, ``valid_from``, ``valid_to``,
  ``garages``, ``garages_not_named``, ``unreadable``, ``unreadable_garages``,
  ``registrations`` (each ``vehicle_identity``, ``garage``, ``effective_day``,
  ``end_day``, ``ended_reason``). A refusal is JSON on stdout
  (``{"refused": code, "field": ..., "detail": ...}``), exit 3. The machine's
  configuration is a sentence on stderr, exit 2.

garage-pass (``show-garage-register --tenant T --garage G``)
  the same exits; read for its ``codes`` alone (each ``pass``, ``state``,
  ``bound_identity``, ``exit_only``), because ``show-pass`` carries no
  exit-only flag and a car garage-pass has replaced on the pass is not live.

monthly-billing (``show-register --tenant T --agreement A``)
  exit 0, JSON on stdout, nine keys: ``agreement``, ``version``, ``registrar``,
  ``status``, ``cancelled_effective_day``, ``home_garage``, ``covered_garages``,
  ``registrations`` (each ``garage``, ``identity_normalised``),
  ``garages_not_covered``. A refusal or NOT FOUND is a sentence on stderr,
  exit 2 (``REFUSED — <code>: ...`` or ``NOT FOUND — ...``). No DSN is a
  sentence and exit 1; a DSN that does not connect is the driver's own
  traceback, exit 1 -- both read here as configuration.

monthly-billing (``register-vehicle --tenant T --agreement A --vehicle V --at I``
and ``release-vehicle --tenant T --agreement A --vehicle V --garage G``)
  exit 0, a first line saying what was done, then ONE LINE PER GARAGE THE
  CALL REACHED, exactly ``  at garage {garage id}: {stored form}``
  (``cli.py:365`` at the pinned commit): every covered garage for a register,
  the ONE named garage for a release. That line is the one piece of prose the
  connector relies on, and ``STORED_FORM_LINE`` pins its spelling. It is
  matched against the garage ids the register read already named -- the
  garage is a known string, so the form after it may contain anything, ``: ``
  included. A line naming no known garage is unparseable and is reported as
  such, never guessed at.

  **Every release names its garage.** ``release-vehicle`` without ``--garage``
  releases by identity at EVERY covered garage under each garage's own rule
  (measured at the pinned commit): passing a stale exact-rule form back would
  also take the live folded-rule row that spells the same at another garage.
  With ``--garage G`` the door normalises the text under G's rule and deletes
  at G alone, so a stored form passed back at the garage that stored it takes
  exactly that row. The connector never calls the door's fan-out.

  **An ambiguous covered set is refused before the line is read.** When one
  covered id is another covered id plus the separator plus anything (``g`` and
  ``g: 2``), a line ``  at garage g: 2: x1`` has two readings and no parser can
  tell them apart; ``ambiguous_garage_ids`` names such pairs and the link is
  refused before any write, so the parser is never asked that question.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass

from pass_billing_connector.findings import (
    FINDING_GARAGE_PASS_CONFIGURATION,
    FINDING_GARAGE_PASS_REFUSED,
    FINDING_GARAGE_PASS_UNPARSEABLE,
    FINDING_MONTHLY_BILLING_CONFIGURATION,
    FINDING_MONTHLY_BILLING_REFUSED,
    FINDING_MONTHLY_BILLING_UNPARSEABLE,
    OUTCOME_DONE,
    OUTCOME_FAILED,
    OUTCOME_REFUSED,
    OUTCOME_UNPARSEABLE,
)

GARAGE_PASS = "garage-pass"
MONTHLY_BILLING = "monthly-billing"
SCRIPTS: tuple[str, ...] = (GARAGE_PASS, MONTHLY_BILLING)

#: The door's per-garage line, PINNED. ``{garage}`` is a known garage id and
#: ``{form}`` is the rest of the line, whatever it contains.
STORED_FORM_LINE = "  at garage {garage}: {form}"
_LINE_HEAD = STORED_FORM_LINE.split("{garage}")[0]
_LINE_SEPARATOR = STORED_FORM_LINE.split("{garage}")[1].split("{form}")[0]

#: garage-pass's exit statuses, from its command line's docstring.
GARAGE_PASS_EXIT_REFUSED = 3
GARAGE_PASS_EXIT_CONFIGURATION = 2
#: monthly-billing's: every refusal and NOT FOUND is 2.
MONTHLY_BILLING_EXIT_REFUSED = 2


class ScriptMissing(Exception):
    """A console script the connector needs is not on PATH. A sentence, exit 2."""


def require_scripts() -> None:
    """Refuse by name, before any link is read, if either script is absent."""
    missing = [name for name in SCRIPTS if shutil.which(name) is None]
    if missing:
        raise ScriptMissing(
            f"the console script(s) {missing} are not on PATH. The connector drives the two "
            "modules through their command lines and does nothing without them: install "
            "openparking-garage-pass[store] and openparking-monthly-billing[store]."
        )


@dataclass(frozen=True)
class Read:
    """A module's answer to a read: the document, or the finding that stands
    in for it. ``detail`` carries the module's own words either way."""

    document: dict | None
    finding: str | None
    detail: str | None

    @property
    def ok(self) -> bool:
        return self.document is not None


@dataclass(frozen=True)
class Answer:
    """The door's answer to a write: what it stored per garage, or why not."""

    outcome: str
    stored: dict[str, str]
    reason: str | None


def _run(argv: list[str]) -> subprocess.CompletedProcess:
    # The environment is inherited as it is: the modules' DSNs are theirs to
    # read, and the connector adds nothing and reads nothing.
    return subprocess.run(argv, capture_output=True, text=True, check=False)


def _json_or_none(text: str) -> dict | None:
    try:
        document = json.loads(text)
    except ValueError:
        return None
    return document if isinstance(document, dict) else None


# ---------------------------------------------------------------- garage-pass


def show_pass(tenant: str, garage: str, pass_id: str) -> Read:
    return _garage_pass_read(_run([GARAGE_PASS, "show-pass", "--tenant", tenant, "--garage",
                                   garage, "--pass-id", pass_id]))


def show_garage_register(tenant: str, garage: str) -> Read:
    """The garage's register, read for its ``codes`` alone: ``show-pass`` carries
    no exit-only flag, and this is where garage-pass publishes it, per QR
    (``live.exit_only_identities``)."""
    return _garage_pass_read(_run([GARAGE_PASS, "show-garage-register", "--tenant", tenant,
                                   "--garage", garage]))


def _garage_pass_read(done: subprocess.CompletedProcess) -> Read:
    if done.returncode == 0:
        document = _json_or_none(done.stdout)
        if document is None:
            return Read(None, FINDING_GARAGE_PASS_UNPARSEABLE, _printed(done))
        return Read(document, None, None)
    if done.returncode == GARAGE_PASS_EXIT_REFUSED:
        refused = _json_or_none(done.stdout)
        detail = json.dumps(refused, sort_keys=True) if refused else _printed(done)
        return Read(None, FINDING_GARAGE_PASS_REFUSED, detail)
    return Read(None, FINDING_GARAGE_PASS_CONFIGURATION, _printed(done))


# ------------------------------------------------------------ monthly-billing


def show_register(tenant: str, agreement: str) -> Read:
    done = _run([MONTHLY_BILLING, "show-register", "--tenant", tenant, "--agreement", agreement])
    if done.returncode == 0:
        document = _json_or_none(done.stdout)
        if document is None:
            return Read(None, FINDING_MONTHLY_BILLING_UNPARSEABLE, _printed(done))
        return Read(document, None, None)
    if done.returncode == MONTHLY_BILLING_EXIT_REFUSED:
        return Read(None, FINDING_MONTHLY_BILLING_REFUSED, _printed(done))
    return Read(None, FINDING_MONTHLY_BILLING_CONFIGURATION, _printed(done))


def register_vehicle(tenant: str, agreement: str, identity: str, at: str,
                     garages: tuple[str, ...]) -> Answer:
    done = _run([MONTHLY_BILLING, "register-vehicle", "--tenant", tenant, "--agreement",
                 agreement, "--vehicle", identity, "--at", at])
    return _door_answer(done, garages)


def release_vehicle(tenant: str, agreement: str, form: str, garage: str,
                    garages: tuple[str, ...]) -> Answer:
    """Release ONE stored form at the ONE covered garage that stores it. The
    garage is always named: the door's unnamed release fans out by identity
    over every covered garage, and the connector never asks for that."""
    done = _run([MONTHLY_BILLING, "release-vehicle", "--tenant", tenant, "--agreement",
                 agreement, "--vehicle", form, "--garage", garage])
    return _door_answer(done, garages)


def _door_answer(done: subprocess.CompletedProcess, garages: tuple[str, ...]) -> Answer:
    if done.returncode == 0:
        stored = stored_forms(done.stdout, garages)
        if stored is None:
            return Answer(OUTCOME_UNPARSEABLE, {}, _printed(done))
        return Answer(OUTCOME_DONE, stored, None)
    if done.returncode == MONTHLY_BILLING_EXIT_REFUSED:
        return Answer(OUTCOME_REFUSED, {}, _printed(done))
    return Answer(OUTCOME_FAILED, {}, _printed(done))


def stored_forms(stdout: str, garages: tuple[str, ...]) -> dict[str, str] | None:
    """The per-garage lines of a door answer, as ``{garage: form}``.

    Every line after the first is one of the pinned shape naming a KNOWN
    garage, or the answer is unparseable (``None``): a garage the read did not
    name, a line of another shape, a garage named twice. The door prints one
    line per covered garage and the register read named the covered set, so
    a garage missing from the answer is not an error here -- the caller
    compares against the covered set itself.
    """
    lines = stdout.splitlines()
    if not lines:
        return None
    stored: dict[str, str] = {}
    for line in lines[1:]:
        garage, form = _parse_line(line, garages)
        if garage is None or garage in stored:
            return None
        stored[garage] = form
    return stored


def ambiguous_garage_ids(garages: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    """Every (shorter, longer) pair of known ids where the longer one begins
    with the shorter one PLUS THE SEPARATOR -- the one shape of covered set in
    which a printed line has two readings. Sorted; empty for every set the
    parser can read without guessing."""
    return tuple(sorted(
        (shorter, longer)
        for shorter in garages for longer in garages
        if longer != shorter and longer.startswith(shorter + _LINE_SEPARATOR)
    ))


def _parse_line(line: str, garages: tuple[str, ...]) -> tuple[str | None, str]:
    if not line.startswith(_LINE_HEAD):
        return None, ""
    rest = line[len(_LINE_HEAD):]
    # The longest known garage id that the line continues from, so a garage
    # id that is a prefix of another cannot claim the other's line.
    for garage in sorted(garages, key=len, reverse=True):
        head = garage + _LINE_SEPARATOR
        if rest.startswith(head):
            return garage, rest[len(head):]
    return None, ""


def _printed(done: subprocess.CompletedProcess) -> str:
    out = done.stdout.strip()
    err = done.stderr.strip()
    parts = [p for p in (out, err) if p]
    return f"exit {done.returncode}: " + (" | ".join(parts) if parts else "(nothing printed)")
