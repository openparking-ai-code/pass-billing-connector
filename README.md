# Open Parking AI — pass-billing connector

**For each stated link — a garage pass on one side, an outside-registrar
agreement in monthly billing on the other — on the day given, make billing's
register for that agreement equal the pass's live register, and say loudly
whatever cannot be made equal.** That one question, and nothing else. Billing's
register is current state with no effective time — a release takes effect when
it is made — so a run given a past instant makes *today's* billing register
equal that past day's live register, and the next run for today repairs it.

```
$ pass-billing-connector sync --links links.json --at 2026-09-16T09:00:00-06:00
```

One verb. The instant is required, ISO with an offset; the day compared with
garage-pass's days is the date of that instant as written. The report is one
JSON document with sorted keys: every link, every register and release the
run made with its reason, every finding by name. Exit 0 when every link's
billing register equals its pass's live register on the final read; 1 when
at least one does not; 2 when the connector itself could not run.

## Why a module, and why this shape

`garage-pass` and `monthly-billing` are standalone, and both name "the
integrator" as the party outside. The correspondence between a pass and an
agreement, and the cross-database ordering of the writes, live here — in a
third module, and in neither of the two.

**The command lines are the only door.** The connector runs `garage-pass`
and `monthly-billing` as subprocesses and reads what they print. It imports
neither package, opens no database connection, holds no DSN — the two
modules read their own from the environment it passes through untouched —
and has **no database of its own**: nothing it needs survives between runs,
so a third store would be a third thing to keep consistent. That is a
guarantee with a control, not a sentence: the source is scanned for an
import of either package, a database driver, an environment read and a
`migrations/` directory, and each has a plant that reddens the suite.

**Links are stated, never inferred.** A links document names each pass and
each agreement, by tenant and id. The two databases share no key, and the
connector never guesses a link from matching text.

**A replaced car is not live.** After `replace-car`, garage-pass keeps the
old car's registration open and marks only its QR exit only: the car may not
enter, and it still gets out. `show-pass` carries no exit-only flag, so the
connector reads it from the QRs `show-garage-register` publishes. Billing's
register has no direction, so the old car leaves it.

**Registers first, releases by stored form.** Every identity live on the day
is registered through billing's door, as garage-pass recorded it, and the
stored form per garage is taken from what the door prints back. Then every
row billing holds that no live identity produced is released by passing that
form back at the one garage that stores it (`release-vehicle --garage`), so
no release ever reaches another garage's row. The connector never
reimplements billing's normalisation — the door's answer is the only source
of a form it has. Two live identities that
fold to one form at a garage are a **collision**: nothing is released for
that link, and the run says so. A live identity whose register the door did
not answer `done` — refused, failed, or unreadable — stops the link's
releases the same way: the connector cannot tell "not registered" from "the
door did not tell me", so a car billing already holds keeps its rows, the
finding names the identity, and the next run re-reads. A *refused* register —
a car held by another agreement — is not transient: it stands until an
operator moves the car, and until then that link releases nothing on every
run, saying so each time. That is the rule holding, not a fault. A car moving
between two linked passes is the one case the run settles itself: when
another link of the same run released a row after the held link ran, the held
link is run once more, from fresh reads, before the run ends.

**The verdict is the final read.** After the writes both sides are read
again. Any difference is a divergence, named per link, per garage, per form,
with the side that holds it; and the refusals of step 1 are checked again
against the final reads, so a covered set or a registrar that moved under the
run is named and the link does not converge. The report claims nothing the
run could not learn: a row left beside an identity whose form the run never
got is named as one whose owner is not known, not as a row the pass stores
nothing in. A run killed half-way is repaired by the next run from fresh
reads.

**Nothing personal travels**, and **nothing here can refuse an exit**: the
connector touches registrations only, and garage-pass's own access answer at
a lane is the same before and after a run.

## Every guarantee has a control that has been proven to fire

```
python scripts/fail_controls.py --anchors   # every anchor is live, in a second
python scripts/fail_controls.py             # break each guarantee, require RED
```

The guarantees, the finding codes, the exit codes, the report's keys, the
links document's keys and the pinned commits are generated into
`docs/CONTRACT.md` from the registries and the source. No number in it is
typed.

## Install

```
pip install -e .              # the connector: no dependencies at all
pip install -e '.[dev]'       # plus pytest, ruff and the two modules at their pinned commits
```

Python 3.11 or newer. At runtime the connector needs the two console scripts
on `PATH` — `garage-pass` and `monthly-billing`, each installed with its
`store` extra — and their DSNs in the environment (`GARAGE_PASS_DSN`,
`MONTHLY_BILLING_DSN`). It refuses by name without the scripts.

## The tests

The suite drives two real databases, one per module, each migrated from the
commit `pyproject.toml` pins, through the two command lines:

```
PASS_BILLING_CONNECTOR_TEST_DSN='host=localhost user=postgres password=postgres dbname=postgres' pytest -q
```

The harness creates `pbc_garage_pass_test` and `pbc_monthly_billing_test` in
that cluster, fetches each pinned commit's `migrations/` into `.pins/`
(gitignored; `git fetch` and `git archive`, never a checkout), and drops both
databases at the end of the session. What has no verb in either module — a
tenant, billing's garages and agreements — the harness seeds the way the
modules' own harnesses do; everything else goes through the command lines.

## What is not here

No reservation seam. No transient or per-park account. No serialisation of
two runs over one link at once — the operator runs one at a time per link,
and a run whose final read disagrees exits 1. No change to either module: the
connector is built against the commits it pins and reaches them through their
published surfaces only.

## Contributing

Open Parking AI does not accept outside contributions. Pull requests, issues and comments are limited to the maintainers.

## Licence

AGPL-3.0-or-later. See `LICENSE`.

Built by 72 Knots Method by 72Knots.ai
