#!/usr/bin/env python3
"""Generate docs/CONTRACT.md from the registries, and check it has not drifted.

    python scripts/generate_contract.py            # write the document
    python scripts/generate_contract.py --check    # fail if it would change

**WHAT ``--check`` WRITES.** Nothing: it renders in memory and compares. This
generator needs no database -- every block is derived from source that is
already on disk: the guarantees from ``tests/_guarantees.py``; the finding
codes, sides, actions, outcomes, reasons and exit codes from ``findings.py``;
the report's keys from the dataclasses in ``report.py``; the links document's
keys from ``links.py``; the verbs from ``cli.py``; the door's pinned line and
the exit statuses read from each module from ``doors.py``; the pinned commits
from ``pyproject.toml``. A number or a sentence edited by hand turns
``--check`` red. CI's independent check is ``git diff --exit-code
docs/CONTRACT.md`` after a plain run.

**AND GENERATION IS NOT VERIFICATION.** Moving a sentence from a document into
a template does not stop it being hand-written -- everywhere except the holes
it is still prose nobody checks. A generated block asserts only what it
DERIVES from its values. So ``tests/test_contract_is_generated.py`` plants
values that contradict the prose and requires the prose to change; anything
that survives that plant is a fixed string, and a fixed string is marked as
design documentation rather than left looking measured.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from _guarantees import GUARANTEES, guarantee_ids  # noqa: E402

DOC = ROOT / "docs" / "CONTRACT.md"
BEGIN = "<!-- GENERATED:{name} -->"
END = "<!-- END:{name} -->"


def block_guarantees() -> str:
    rows = ["| id | what is guaranteed |", "|---|---|"]
    for gid in guarantee_ids():
        rows.append(f"| **{gid}** | {GUARANTEES[gid]} |")
    rows.append("")
    rows.append(
        f"That is {len(GUARANTEES)} guarantees. Every one of them has a fail control "
        "that has been proven to fire, and the count above is derived from the "
        "registry rather than typed here."
    )
    return "\n".join(rows)


def block_pins() -> str:
    """The two commits the connector was built against, from pyproject.toml."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    rows = ["| module | commit |", "|---|---|"]
    found = 0
    for requirement in project["optional-dependencies"]["dev"]:
        match = re.fullmatch(
            r"openparking-([a-z-]+)\[store\] @ git\+https://github\.com/openparking-ai/"
            r"([a-z-]+)@([0-9a-f]{40})",
            requirement,
        )
        if match:
            rows.append(f"| `{match.group(1)}` | `{match.group(3)}` |")
            found += 1
    rows.append("")
    rows.append(
        f"{found} module{'s are' if found != 1 else ' is'} pinned, as a DEV dependency for the "
        "tests. At runtime the connector needs the two console scripts on PATH and imports "
        "neither package; the runtime dependency list is "
        f"{'empty' if not project['dependencies'] else project['dependencies']}."
    )
    return "\n".join(rows)


BLOCKS = {
    "guarantees": block_guarantees,
    "pins": block_pins,
}


def _module_blocks() -> dict:
    """The blocks that read the connector's own source."""
    from pass_billing_connector import cli, doors, findings, links, report

    def block_findings() -> str:
        rows = ["| code | what it means |", "|---|---|"]
        for code, sentence in sorted(findings.FINDINGS.items()):
            rows.append(f"| `{code}` | {sentence} |")
        rows.append("")
        rows.append(
            f"That is {len(findings.FINDINGS)} findings. A divergence names its side: "
            + "; ".join(f"`{s}` -- {m}" for s, m in sorted(findings.SIDES.items()))
            + "."
        )
        return "\n".join(rows)

    def block_actions() -> str:
        lines = ["**Actions** -- what a run can do to billing's register:", ""]
        for action, sentence in sorted(findings.ACTIONS.items()):
            lines.append(f"- `{action}` -- {sentence}")
        lines += ["", "**Outcomes** -- what the door said:", ""]
        for outcome, sentence in sorted(findings.OUTCOMES.items()):
            lines.append(f"- `{outcome}` -- {sentence}")
        lines += ["", "**Reasons** -- why the action was made:", ""]
        for reason, sentence in sorted(findings.REASONS.items()):
            lines.append(f"- `{reason}` -- {sentence}")
        return "\n".join(lines)

    def block_exits() -> str:
        rows = ["| exit | meaning |", "|---|---|"]
        for code, sentence in sorted(findings.EXITS.items()):
            rows.append(f"| **{code}** | {sentence} |")
        return "\n".join(rows)

    def block_report_keys() -> str:
        lines = []
        for name, keys in report.report_keys().items():
            lines.append(f"- `{name}`: " + ", ".join(f"`{k}`" for k in keys))
        total = sum(len(k) for k in report.report_keys().values())
        lines += [
            "",
            f"That is {total} keys across {len(report.report_keys())} shapes, derived from the "
            "dataclasses that render the report, and every key is present on every instance "
            "(`null` when it does not apply). Nothing personal travels: ids, garages, days, "
            "identities and stored forms are the whole of it.",
        ]
        return "\n".join(lines)

    def block_links() -> str:
        keys = ", ".join(f"`{k}`" for k in links.LINK_KEYS)
        return (
            f"A links document is an object with exactly one key, `{links.TOP_KEY}`, whose "
            f"value is a list of links. A link carries exactly these {len(links.LINK_KEYS)} "
            f"keys, every one non-blank text: {keys}. Any other key is refused rather than "
            "ignored, a missing key is refused, the two tenants are uuids, and a pass or an "
            "agreement appearing in two links is refused -- each by name, before anything is "
            "read from either module. `pass_garage` is an access key, not a scope."
        )

    def block_verbs() -> str:
        verbs = ", ".join(f"`{v}`" for v in cli.VERBS)
        return (
            f"The command line has {len(cli.VERBS)} verb{'s' if len(cli.VERBS) != 1 else ''}: "
            f"{verbs}. There is no exit verb and no field of the report that could deny an "
            "exit: the connector touches registrations only."
        )

    def block_doors() -> str:
        scripts = ", ".join(f"`{s}`" for s in doors.SCRIPTS)
        return (
            f"The connector runs {len(doors.SCRIPTS)} console scripts as subprocesses -- "
            f"{scripts} -- and reads what they print. The one non-JSON line it relies on is "
            f"the door's per-garage answer, pinned as `{doors.STORED_FORM_LINE}`. It reads "
            f"garage-pass's exit {doors.GARAGE_PASS_EXIT_REFUSED} as a refusal and its exit "
            f"{doors.GARAGE_PASS_EXIT_CONFIGURATION} as configuration; monthly-billing's exit "
            f"{doors.MONTHLY_BILLING_EXIT_REFUSED} as a refusal or NOT FOUND, and any other "
            "non-zero status as configuration."
        )

    return {
        "findings": block_findings,
        "actions": block_actions,
        "exits": block_exits,
        "report-keys": block_report_keys,
        "links": block_links,
        "verbs": block_verbs,
        "doors": block_doors,
    }


BLOCKS.update(_module_blocks())


def render(template: str) -> str:
    out = template
    for name, builder in BLOCKS.items():
        begin, end = BEGIN.format(name=name), END.format(name=name)
        if begin not in out or end not in out:
            raise SystemExit(f"docs/CONTRACT.md has no {begin} ... {end} block")
        head, rest = out.split(begin, 1)
        _stale, tail = rest.split(end, 1)
        out = f"{head}{begin}\n{builder()}\n{end}{tail}"
    return out


def main(argv: list[str]) -> int:
    current = DOC.read_text()
    generated = render(current)
    if "--check" in argv:
        if current != generated:
            print(
                "docs/CONTRACT.md does not match its generator. A number or a "
                "sentence inside a generated block was edited by hand, or the "
                "registry it comes from moved. Run this script with no arguments."
            )
            return 1
        print("docs/CONTRACT.md is the generated one.")
        return 0
    DOC.write_text(generated)
    print(f"wrote {DOC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
