"""The pass's live register on day D, from what ``show-pass`` printed.

**THE READ DERIVES NOTHING, SO THIS DOES.** garage-pass's read uses no clock:
it shows the stored state and the two valid days and every registration row,
history included, and leaves the day to the reader. This is the reader.

A pass's live register on day D is EMPTY unless its stored ``state`` is
``active`` and D lies within ``valid_from..valid_to`` -- inclusive days, a
``null`` bound unbounded. A draft, an awaiting-enrolment, a suspended, a
revoked or an out-of-days pass keeps no car in billing's register: billing's
door is for cars a pass covers, and those passes cover none.

Within that, a registration row is live on D when ``effective_day <= D`` and
(``end_day`` is null or ``D < end_day``): ``end_day`` is the day the identity
is free FROM (garage-pass's ``end-registration``), so a row ending today is
not live today, and one effective tomorrow is not live today.

**A CAR GARAGE-PASS HAS REPLACED ON THE PASS IS NOT LIVE.** ``replace-car``
leaves the old car's registration open and marks only its QR exit only: the
car may not enter, and garage-pass still lets it out. ``show-pass`` carries
no exit-only flag, so the connector reads it from the ``codes`` of
``show-garage-register`` (``exit_only_identities``). Billing's register has
no direction -- a row there covers the car at an entry and at an exit -- so a
car that may not enter is not one billing keeps. The flag is current state,
as billing's register is: it carries no day.

The identity is the identity AS GARAGE-PASS RECORDED IT, byte for byte.
garage-pass strips surrounding whitespace on the way in and normalises
nothing; billing normalises per garage on ITS way in. The connector does
neither -- it hands the recorded text to the door and reads back the form.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

STATE_ACTIVE = "active"
#: A QR's stored state once cancelled (garage-pass's ``CredentialState``).
CODE_CANCELLED = "cancelled"


@dataclass(frozen=True)
class LiveRegister:
    """Per garage the pass names, the identities live there on the day."""

    covers_the_day: bool
    #: garage -> the live identities at it, sorted by code point
    by_garage: dict[str, tuple[str, ...]]

    def identities(self) -> tuple[str, ...]:
        return tuple(sorted({i for ids in self.by_garage.values() for i in ids}))

    def pairs(self) -> frozenset[tuple[str, str]]:
        return frozenset((g, i) for g, ids in self.by_garage.items() for i in ids)


def _day(text: str | None) -> date | None:
    return None if text is None else date.fromisoformat(text)


def covers(shown: dict, day: date) -> bool:
    """Does the pass, as shown, cover the day at all?"""
    if shown.get("state") != STATE_ACTIVE:
        return False
    valid_from = _day(shown.get("valid_from"))
    valid_to = _day(shown.get("valid_to"))
    if valid_from is not None and day < valid_from:
        return False
    if valid_to is not None and day > valid_to:
        return False
    return True


def row_is_live(row: dict, day: date) -> bool:
    effective = _day(row["effective_day"])
    end = _day(row.get("end_day"))
    if effective is None or effective > day:
        return False
    return end is None or day < end


def exit_only_identities(garage_register: dict, pass_id: str) -> frozenset[str]:
    """The cars garage-pass has REPLACED on this pass, from the ``codes`` its
    ``show-garage-register`` prints -- derived as garage-pass derives
    ``exit_only`` for a registration (``registrations_of``): at least one QR
    of the pass bound to the car is exit only, and no QR of the pass bound to
    it is still live (neither cancelled nor exit only). The bound car is the
    text garage-pass printed, compared byte for byte with the registration's
    identity; nothing is normalised here."""
    replaced: set[str] = set()
    still_live: set[str] = set()
    for code in garage_register.get("codes") or ():
        car = code.get("bound_identity")
        if code.get("pass") != pass_id or car is None:
            continue
        if code.get("exit_only"):
            replaced.add(car)
        elif code.get("state") != CODE_CANCELLED:
            still_live.add(car)
    return frozenset(replaced - still_live)


def live_register(shown: dict, day: date,
                  replaced: frozenset[str] = frozenset()) -> LiveRegister:
    garages = tuple(shown.get("garages") or ())
    if not covers(shown, day):
        return LiveRegister(False, {g: () for g in garages})
    by_garage: dict[str, set[str]] = {g: set() for g in garages}
    for row in shown.get("registrations") or ():
        if (row["garage"] in by_garage and row_is_live(row, day)
                and row["vehicle_identity"] not in replaced):
            by_garage[row["garage"]].add(row["vehicle_identity"])
    return LiveRegister(True, {g: tuple(sorted(ids)) for g, ids in by_garage.items()})
