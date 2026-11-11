"""The links document: every link STATED, never inferred.

A link is a pass on one side and an outside-registrar agreement on the other,
in two databases that share no key. The only common ground between them is
text -- a garage's external id, a pass id, an agreement id -- and the connector
never guesses a link from matching text. Somebody writes it down, here.

    {"links": [
      {"pass_tenant": "<uuid>", "pass_id": "pass-1", "pass_garage": "garage-a",
       "billing_tenant": "<uuid>", "agreement_id": "ag-1"}
    ]}

``pass_garage`` is an ACCESS KEY, not a scope: it is the ``--garage`` every
garage-pass store call takes, and garage-pass refuses a garage the pass does
not name (its G25). The connector compares the pass's WHOLE garage set with
the agreement's covered set (``sync.py``); the garage named here decides
nothing about which garages are reconciled.

Unknown keys are refused, a missing key is refused, a pass or an agreement
appearing in two links is refused -- each by name, before anything is read
from either module. A tenant is compared as the uuid both modules read, so
the same tenant typed in another letter case is still the same tenant. The
connector has no database: this document is the whole of what it knows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields
from pathlib import Path
from uuid import UUID


class LinksRefused(Exception):
    """The links document is not of the published shape. A sentence, exit 2."""


@dataclass(frozen=True)
class Link:
    pass_tenant: str
    pass_id: str
    pass_garage: str
    billing_tenant: str
    agreement_id: str


#: The keys a link carries, derived from the class -- the contract lists these.
LINK_KEYS: tuple[str, ...] = tuple(f.name for f in fields(Link))
TOP_KEY = "links"


def load_links(path: str) -> tuple[Link, ...]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise LinksRefused(f"the links document {path!r} cannot be read: {exc}") from None
    try:
        document = json.loads(text)
    except ValueError as exc:
        raise LinksRefused(f"the links document {path!r} is not JSON: {exc}") from None
    return links_from(document)


def links_from(document: object) -> tuple[Link, ...]:
    if not isinstance(document, dict) or set(document) != {TOP_KEY}:
        shape = sorted(document) if isinstance(document, dict) else type(document).__name__
        raise LinksRefused(
            f"the links document is an object with exactly one key, {TOP_KEY!r}; "
            f"this one has {shape}."
        )
    items = document[TOP_KEY]
    if not isinstance(items, list):
        raise LinksRefused(f"{TOP_KEY!r} is a list of links; this one is {type(items).__name__}.")
    links: list[Link] = []
    seen_passes: dict[tuple[str, str], int] = {}
    seen_agreements: dict[tuple[str, str], int] = {}
    for index, item in enumerate(items):
        link = _one_link(index, item)
        pass_key = (_tenant_key(link.pass_tenant), link.pass_id)
        agreement_key = (_tenant_key(link.billing_tenant), link.agreement_id)
        if pass_key in seen_passes:
            raise LinksRefused(
                f"link {index}: pass {link.pass_id!r} of tenant {link.pass_tenant} already "
                f"appears in link {seen_passes[pass_key]}. A pass is linked once, or the two "
                "links would write one register from two."
            )
        if agreement_key in seen_agreements:
            raise LinksRefused(
                f"link {index}: agreement {link.agreement_id!r} of tenant "
                f"{link.billing_tenant} already appears in link {seen_agreements[agreement_key]}. "
                "An agreement's register has one writer, and two links would be two."
            )
        seen_passes[pass_key] = index
        seen_agreements[agreement_key] = index
        links.append(link)
    return tuple(links)


def _tenant_key(tenant: str) -> str:
    """A tenant in the form both modules read it: their ``--tenant`` is a
    uuid, so ``ABC...`` and ``abc...`` are one tenant there, and a duplicate
    is one here however its letters were typed. Only the comparison uses this
    form; the link keeps the text as written."""
    return str(UUID(tenant))


def _one_link(index: int, item: object) -> Link:
    if not isinstance(item, dict):
        raise LinksRefused(f"link {index} is not an object.")
    unknown = sorted(set(item) - set(LINK_KEYS))
    missing = sorted(set(LINK_KEYS) - set(item))
    if unknown:
        raise LinksRefused(
            f"link {index} carries a key the connector does not read: {unknown}. "
            f"A link's keys are exactly {list(LINK_KEYS)}."
        )
    if missing:
        raise LinksRefused(f"link {index} is missing {missing}.")
    values: dict[str, str] = {}
    for key in LINK_KEYS:
        value = item[key]
        if not isinstance(value, str) or not value.strip():
            raise LinksRefused(f"link {index}: {key} is non-blank text; this one is {value!r}.")
        values[key] = value
    for key in ("pass_tenant", "billing_tenant"):
        try:
            UUID(values[key])
        except ValueError:
            raise LinksRefused(
                f"link {index}: {key} is a uuid, the form both modules' --tenant takes; "
                f"this one is {values[key]!r}."
            ) from None
    return Link(**values)
