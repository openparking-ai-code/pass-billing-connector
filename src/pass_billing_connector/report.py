"""The report: one JSON document, sorted keys, every link with every action
and every finding by name.

**THE KEY SET IS DERIVED FROM THESE CLASSES AND IS CLOSED.** ``docs/CONTRACT.md``
lists the keys from the dataclass fields; a key the contract does not list
cannot be emitted without changing a class here, and the test that plants one
requires the contract to change with it. Every key is present on every
instance -- a field that does not apply is ``null`` -- so the shape a reader
parses is the same shape every run.

**NOTHING PERSONAL TRAVELS.** Ids, garages, days, identities and stored forms:
that is the whole of it. ``show-pass`` already carries no holder, label or
term beyond the two valid days, and nothing here adds a field the reads did
not return.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields


@dataclass(frozen=True)
class Finding:
    code: str
    detail: str
    garage: str | None = None
    form: str | None = None
    identity: str | None = None
    identities: tuple[str, ...] = ()
    side: str | None = None


@dataclass(frozen=True)
class Action:
    action: str
    outcome: str
    reason: str
    identity: str | None = None
    form: str | None = None
    #: The ONE covered garage a release named (`release-vehicle --garage`);
    #: null on a register, which the door makes at every covered garage.
    garage: str | None = None
    #: What the door printed per garage, on a `done` outcome.
    stored: dict[str, str] = field(default_factory=dict)
    #: The door's own sentence, on any other outcome.
    detail: str | None = None


@dataclass(frozen=True)
class Row:
    garage: str
    form: str


@dataclass(frozen=True)
class LinkReport:
    pass_tenant: str
    pass_id: str
    pass_garage: str
    billing_tenant: str
    agreement_id: str
    converged: bool
    #: True when the link was refused before any write (K5.1 or a read that
    #: did not answer): the actions list is then empty by construction. A link
    #: run a second time whose second attempt is refused is reported as its
    #: first attempt, not refused (``sync``).
    refused: bool
    #: The pass's live register on the day, per garage, from the FINAL read.
    live: dict[str, tuple[str, ...]]
    #: What billing's register is expected to hold: each live identity's
    #: stored form per covered garage, as the door answered.
    expected: tuple[Row, ...]
    #: What billing's register holds on the FINAL read.
    billing: tuple[Row, ...]
    actions: tuple[Action, ...]
    findings: tuple[Finding, ...]


@dataclass(frozen=True)
class Report:
    at: str
    day: str
    converged: bool
    links: tuple[LinkReport, ...]

    def as_document(self) -> dict:
        return asdict(self)

    def rendered(self) -> str:
        return json.dumps(self.as_document(), sort_keys=True, indent=2, ensure_ascii=False)


def report_keys() -> dict[str, tuple[str, ...]]:
    """Every key the report can carry, per class -- read by the contract."""
    return {
        cls.__name__: tuple(f.name for f in fields(cls))
        for cls in (Report, LinkReport, Action, Finding, Row)
    }
