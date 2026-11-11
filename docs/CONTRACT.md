# The contract — Open Parking AI pass-billing connector

What this module guarantees, in sentences somebody could act on. The marked
blocks below are GENERATED (`scripts/generate_contract.py`) from the registry
in `tests/_guarantees.py`, from the code that implements it and from
`pyproject.toml`; CI fails when the document and its generator disagree.
Nothing in a generated block is typed by hand.

## The question

For each stated link — a garage pass in `garage-pass` on one side, an
agreement whose registrar is `outside` in `monthly-billing` on the other — on
the day given, make billing's register for that agreement equal the pass's
live register, and say loudly whatever cannot be made equal.

## The pinned modules

<!-- GENERATED:pins -->
| module | commit |
|---|---|
| `garage-pass` | `253249b5eb52770ec14d026f04f2c39749b75530` |
| `monthly-billing` | `447f83c312158c0687b243756378b2d8be1b454f` |

2 modules are pinned, as a DEV dependency for the tests. At runtime the connector needs the two console scripts on PATH and imports neither package; the runtime dependency list is empty.
<!-- END:pins -->

## The doors

<!-- GENERATED:doors -->
The connector runs 2 console scripts as subprocesses -- `garage-pass`, `monthly-billing` -- and reads what they print. The one non-JSON line it relies on is the door's per-garage answer, pinned as `  at garage {garage}: {form}`. It reads garage-pass's exit 3 as a refusal and its exit 2 as configuration; monthly-billing's exit 2 as a refusal or NOT FOUND, and any other non-zero status as configuration.
<!-- END:doors -->

The environment the operator gives the connector is passed to those scripts
untouched: `GARAGE_PASS_DSN` and `MONTHLY_BILLING_DSN` are the modules' own
to read, and the connector reads no environment variable at all. Each module
keeps its own transaction boundary and its own row security.

## The command line

<!-- GENERATED:verbs -->
The command line has 1 verb: `sync`. There is no exit verb and no field of the report that could deny an exit: the connector touches registrations only.
<!-- END:verbs -->

```
pass-billing-connector sync --links links.json --at 2026-09-16T09:00:00-06:00
```

No clock: the instant is required, ISO with an offset. The day compared with
garage-pass's days is the DATE OF THAT INSTANT AS WRITTEN, not converted to
any garage's zone — garage-pass's own convention for a registration's
`effective_day`. The same instant reaches billing's `register-vehicle --at`.
The consequence, across garages in different zones: garage-pass's lane door
reads a registration on the garage's local day, while the run reads it on
the day as written; billing's lane reads no day from a registration at all —
a row is current state from the moment it is written until it is released,
present at every instant asked, earlier or later than the instant its door
was given, and the instant reaches the agreement's own axes, never the row.
At an instant that is already tomorrow at one garage,
a car effective tomorrow is not yet live to the run and not in billing, yet
garage-pass's lane at that garage already answers covered — and a car ending
tomorrow is the mirror. For the length of the zone gap the two lanes can
answer differently for the same car at that garage, with the run converged.
That is the rule, not a fault.
`release-vehicle` takes no instant at the pinned commit: billing's register is
current state with no effective time, so a release takes effect when it is
made, and what billing holds after a run is the live set as of the moment the
run ends. A fixture replaying a past day proves billing ends equal to the
pass's register for that day.

## The links document

<!-- GENERATED:links -->
A links document is an object with exactly one key, `links`, whose value is a list of links. A link carries exactly these 5 keys, every one non-blank text: `pass_tenant`, `pass_id`, `pass_garage`, `billing_tenant`, `agreement_id`. Any other key is refused rather than ignored, a missing key is refused, the two tenants are uuids, and a pass or an agreement appearing in two links is refused -- each by name, before anything is read from either module. `pass_garage` is an access key, not a scope.
<!-- END:links -->

## The exits

<!-- GENERATED:exits -->
| exit | meaning |
|---|---|
| **0** | every link's billing register equals its pass's live register on the final read |
| **1** | at least one link's does not -- a refusal, a collision, a divergence, or a module that would not answer. The report says which, per link |
| **2** | the connector itself could not run: the links document is missing, not JSON, or not of the published shape; `--at` is not an ISO instant with an offset; a console script is not on PATH. A sentence on stderr, no report |
<!-- END:exits -->

## The order of a run, per link

1. Read both sides. Refuse the link, writing nothing, on anything that makes
   "equal" undefined (the refusing findings below) — including a covered set
   in which one garage id is another plus the door's separator plus anything
   (`g` and `g: 2`), the one shape the door's printed line cannot be read
   from without guessing.
2. Register every identity live on the day, as garage-pass recorded it; take
   the stored form per garage from the door's printed answer. The connector
   never reimplements billing's normalisation. A car garage-pass has replaced
   on the pass (`replace-car`: its QR is exit only, read from the `codes` of
   `show-garage-register`, because `show-pass` carries no such flag) is not
   live: garage-pass still lets it out, and billing, whose register has no
   direction, does not keep it.
3. Two live identities with one stored form at one garage are a collision:
   nothing is released for the link. A live identity whose register did not
   come back `done` (refused, failed, unreadable) has no known forms and stops
   the link's releases the same way: nothing is released for the link that
   run, the registers that did answer stand, `STORED_FORM_UNKNOWN` names the
   identity and what the door said, and the next run re-reads. **A refused
   register is not transient**: a car held by another agreement stays held
   until an operator moves it, and until then this link releases nothing on
   every run — loudly, each run: exit 1, the finding, the identity, the
   door's words. That is the rule holding, not a fault of the connector's; a
   link that never converges for this reason is waiting on the operator. A
   car moving between two linked passes does not wait: when another link of
   the same run released a row after this link ran, this link is run once
   more, from fresh reads, before the run ends; its report keeps both
   attempts' actions and takes its findings and verdict from the second. A
   second attempt refused at its read (a module that did not answer, or a
   refusal of step 1 that began between the attempts) wrote nothing: the
   report is then the first attempt's, not refused, with its actions and the
   second attempt's findings added, and the link does not converge.
4. Release every row billing holds whose (garage, form) no live identity
   produced, by passing that form back **at that garage**
   (`release-vehicle --garage`): one row per door call, and no other garage's
   row is reached. The door's unnamed release, which fans out by identity
   over every covered garage, is never called, so no release of the
   connector's takes a live car's row and billing answers COVERED for a live
   car at every garage after every door call of a run.
5. Read both again. The verdict is the final read — and step 1's refusals
   are checked again against the final reads: one that fails there is named
   as at the start of a run, and the link does not converge. The report
   claims nothing the run could not learn: a row billing holds that no known
   form accounts for, while some live identity's stored form is unknown, may
   be that identity's — its `DIVERGENCE` line names the identities whose
   forms are unknown (`identities`) and does not call the row foreign.

**Stated limit.** Two runs over one link at once are not serialised by the
connector; the operator runs one at a time per link, and a run whose final
read disagrees exits 1.

## The report

<!-- GENERATED:report-keys -->
- `Report`: `at`, `day`, `converged`, `links`
- `LinkReport`: `pass_tenant`, `pass_id`, `pass_garage`, `billing_tenant`, `agreement_id`, `converged`, `refused`, `live`, `expected`, `billing`, `actions`, `findings`
- `Action`: `action`, `outcome`, `reason`, `identity`, `form`, `garage`, `stored`, `detail`
- `Finding`: `code`, `detail`, `garage`, `form`, `identity`, `identities`, `side`
- `Row`: `garage`, `form`

That is 33 keys across 5 shapes, derived from the dataclasses that render the report, and every key is present on every instance (`null` when it does not apply). Nothing personal travels: ids, garages, days, identities and stored forms are the whole of it.
<!-- END:report-keys -->

<!-- GENERATED:actions -->
**Actions** -- what a run can do to billing's register:

- `register` -- `monthly-billing register-vehicle` for one live identity of the pass, as garage-pass recorded it, at the instant given
- `release` -- `monthly-billing release-vehicle --garage` for one stored form billing holds at ONE covered garage that no live identity stores in there; the action names the garage

**Outcomes** -- what the door said:

- `done` -- the door answered, exit 0, in lines the connector reads; `stored` carries what it printed per garage
- `failed` -- the door exited with a status that is neither 0 nor 2 (no DSN, a database that did not connect); `detail` carries what it printed
- `refused` -- the door refused by name, exit 2; `detail` carries its sentence
- `unparseable` -- the door exited 0 but what it printed is not the `  at garage {id}: {form}` lines the connector reads, so nothing is known about what it did; `detail` carries what it printed and the final read decides

**Reasons** -- why the action was made:

- `billing holds this form; no live identity stores in it` -- billing's register holds the form at this garage and no live identity of the pass stores in it there
- `live on the day` -- the identity is in the pass's live register on the day
<!-- END:actions -->

## The findings

<!-- GENERATED:findings -->
| code | what it means |
|---|---|
| `COLLISION` | Two live identities of the pass have ONE stored form at one garage under that garage's rule. Releasing either would take out the other, so NOTHING is released for this link and it does not converge. The finding names the garage, the form and both identities. |
| `DIVERGENCE` | After the run's writes, the final read of billing's register differs from the pass's live register: one (garage, form) that is on one side only. Exit 1. The finding names the garage, the form and which side holds it. A `billing_only` row while some live identity's stored form is unknown to the run (`STORED_FORM_UNKNOWN`) may be that identity's: the run cannot tell, so the finding's sentence says so, `identities` names whose forms are unknown, and the row is not called foreign. |
| `GARAGE_IDS_AMBIGUOUS` | One covered garage's id is another covered garage's id plus the door's separator (`: `) plus anything -- `g` and `g: 2` -- so the door's printed line `  at garage {id}: {form}` has two readings and no parser can tell them apart. The finding names each such pair, and the parser is never asked the question. On the link's first read it refuses the link before any write. On a later read of the run -- the final read, or a second attempt's read -- the writes already made stand, the link's actions list them, and the link does not converge. |
| `GARAGE_PASS_CONFIGURATION` | garage-pass answered with a configuration sentence (its exit 2: no DSN, a database that did not connect). The finding carries the sentence. When it is the link's first read, the link is refused and nothing was written for it. When it is a later read of the run -- the final read, a second attempt's read, or billing's read before the releases -- the writes already made stand, and the link's actions list them. |
| `GARAGE_PASS_REFUSED` | garage-pass refused the read by name (its exit 3): a wrong tenant, a garage the pass does not name, a pass it does not hold. The finding carries the module's own refusal code and detail. When it is the link's first read, the link is refused and nothing was written for it. When it is a later read of the run -- the final read, a second attempt's read, or billing's read before the releases -- the writes already made stand, and the link's actions list them. |
| `GARAGE_PASS_UNPARSEABLE` | garage-pass exited 0 but what it printed is not the JSON the connector reads. The finding carries the output. When it is the link's first read, the link is refused and nothing was written for it. When it is a later read of the run -- the final read, a second attempt's read, or billing's read before the releases -- the writes already made stand, and the link's actions list them. |
| `GARAGE_SETS_DIFFER` | The garages the pass names and the garages the agreement covers are not the same set, compared as exact text. A link whose two sides disagree on WHERE has no register to make equal. The finding carries both sets. On the link's first read it refuses the link before any write. On a later read of the run -- the final read, or a second attempt's read -- the writes already made stand, the link's actions list them, and the link does not converge. |
| `MONTHLY_BILLING_CONFIGURATION` | monthly-billing exited with a status the connector does not read as a refusal (no DSN, a database that did not connect). The finding carries what it printed. When it is the link's first read, the link is refused and nothing was written for it. When it is a later read of the run -- the final read, a second attempt's read, or billing's read before the releases -- the writes already made stand, and the link's actions list them. |
| `MONTHLY_BILLING_REFUSED` | monthly-billing refused or could not find what the read named (its exit 2: REFUSED or NOT FOUND on stderr) -- a wrong tenant, an agreement it does not hold. The finding carries the module's own sentence. When it is the link's first read, the link is refused and nothing was written for it. When it is a later read of the run -- the final read, a second attempt's read, or billing's read before the releases -- the writes already made stand, and the link's actions list them. |
| `MONTHLY_BILLING_UNPARSEABLE` | monthly-billing exited 0 but what it printed is not the JSON, or not the `  at garage {id}: {form}` lines, the connector reads. The finding carries the output. |
| `PASS_CHANGED_DURING_RUN` | The final read of the pass shows a live register different from the one the run started from. The run wrote for the register it read first; the verdict is against the final one, so the link may not converge until the next run. |
| `PASS_GARAGE_UNREADABLE` | A garage the pass names is stored unreadable in garage-pass (`unreadable_garages`). The finding names the garage and carries garage-pass's own refusal. On the link's first read it refuses the link before any write. On a later read of the run -- the final read, or a second attempt's read -- the writes already made stand, the link's actions list them, and the link does not converge. |
| `PASS_REGISTER_ASYMMETRIC` | On the final read the pass holds an identity live at SOME of its garages and not at others. Billing's door registers a car at every covered garage or at none, so that is a picture billing cannot be made to hold, and the connector's comparison is of the identity set: left unnamed it would converge while billing covered the car at a garage the pass does not. So it is named -- the identity, the garages that hold it, the garages that do not -- the link does not converge, exit 1. The finding is raised on the final read, after the run's own registers and releases, and causes no write of its own: the identity the first read showed live was registered at every covered garage in step 2, as every live identity is, and the next run makes the same register and names it again. Not reachable through garage-pass's own verbs at the pinned commit (a registration is written at every garage of the pass or none, and ended at every one); a row written past them is. |
| `PASS_ROWS_OUTSIDE_ITS_GARAGES` | garage-pass shows a registration row at a garage the pass does not name (`garages_not_named`). The finding names the garages. On the link's first read it refuses the link before any write. On a later read of the run -- the final read, or a second attempt's read -- the writes already made stand, the link's actions list them, and the link does not converge. |
| `PASS_UNREADABLE` | garage-pass holds the pass but cannot read it (`unreadable` on the read is not null), so its valid days are not known. The finding carries garage-pass's own refusal. On the link's first read it refuses the link before any write. On a later read of the run -- the final read, or a second attempt's read -- the writes already made stand, the link's actions list them, and the link does not converge. |
| `REGISTER_ROWS_OUTSIDE_COVERED_SET` | monthly billing shows a registration row at a garage the agreement's latest version does not cover (`garages_not_covered`). The finding names the garages. On the link's first read it refuses the link before any write. On a later read of the run -- the final read, or a second attempt's read -- the writes already made stand, the link's actions list them, and the link does not converge. |
| `REGISTRAR_NOT_OUTSIDE` | The agreement's registrar is not `outside`, so its register is monthly billing's own to write, not the connector's. On the link's first read it refuses the link before any write. On a later read of the run -- the final read, or a second attempt's read -- the writes already made stand, the link's actions list them, and the link does not converge. |
| `STORED_FORM_UNKNOWN` | A live identity's registration did not come back `done` from the door (refused, failed, or an answer the connector cannot read), so its stored form at the covered garages is not known to this run. The finding names the identity and what the door said; the door's own words are on the action. NOTHING IS RELEASED for the link that run -- every row billing may already hold for that identity would look stale, and an incomplete picture of the desired set is never a licence to delete; the registers that did answer stand, and the next run re-reads. The link does not converge. Also raised on the final read for an identity live there that this run did not register. A `refused` register -- a car held by ANOTHER agreement -- is not transient: it stands until an operator moves the car, and until then the link releases nothing on every run, with this finding each time. That is the rule holding, not a fault of the connector's. When another link of the same run released a row after this link ran -- a car moving between two linked passes -- the link is run once more in that run, and the report takes its findings from the second attempt, where this finding stands if that attempt's register did not come back `done` either, or the identity is live only on that attempt's final read. A second attempt refused at its read writes nothing: the report is then the first attempt's, this finding included, with the second attempt's findings after it. |

That is 18 findings. A divergence names its side: `billing_only` -- billing holds a row at this garage in this form; no live identity whose stored form the run learned stores in it there; `pass_only` -- the pass has a live identity storing in this form at this garage; billing holds no such row.
<!-- END:findings -->

## The exit guarantee

The connector touches registrations only. It has no exit verb, no field of
its report could deny an exit, and its subprocess calls are the five verbs
named in C15: three reads and the two registration writes. garage-pass's own
access answer at a lane is the same before and after a run (C15).

## The guarantees

<!-- GENERATED:guarantees -->
| id | what is guaranteed |
|---|---|
| **C1** | Every test module contributes at least one registered guarantee, derived from the filesystem and read from the AST -- so a module cannot be added, skipped or deleted without a guard noticing. A module that PLANTS a defect may not be excused at all. |
| **C2** | docs/CONTRACT.md is GENERATED from this registry and from the code that implements it -- the finding codes, the exit codes, the report's keys, the links document's keys, the verbs, the door's pinned line, the pinned commits -- and its prose is derived rather than fixed: a value that contradicts a published sentence changes the sentence, because generation is not verification. |
| **C3** | THE COMMAND LINES ARE THE ONLY DOOR, AND THERE IS NO DATABASE. The runtime package imports neither module and no database driver, reads no environment variable at all (so no DSN), and has no `migrations/` directory and no runtime dependency -- each read from the source, the tree and the dependency list, never from prose. It runs the two console scripts as subprocesses with the operator's environment passed through untouched, refuses by name (exit 2) when either script is not on PATH, and the two packages installed for the tests are the commits pyproject.toml pins. |
| **C4** | LINKS ARE STATED, NEVER INFERRED. A link carries exactly the published keys, every one non-blank text and the two tenants uuids; an unknown key, a missing key, a pass in two links or an agreement in two links is refused by name before anything is read from either module -- each tenant compared as the uuid both modules read, so one typed in another letter case is the same tenant; and no link is ever guessed from matching ids. `pass_garage` is an access key, not a scope: a garage the pass does not name is garage-pass's own refusal, surfaced by name, and the garage sets compared are the pass's whole set and the agreement's whole covered set. |
| **C5** | ONE VERB, THE INSTANT REQUIRED, THE DAY AS WRITTEN. `sync --links FILE --at INSTANT` is the whole command line; a missing or naive instant is refused, exit 2; the day compared with garage-pass's days is the DATE OF THE INSTANT AS WRITTEN, not converted to any zone; the same instant reaches billing's `register-vehicle --at`. Exit 0 when every link converged on the final read, 1 when at least one did not, 2 only for the connector's own configuration -- a module's refusal or configuration sentence is a finding on its link, exit 1. Links are independent: one broken link stops nothing for the others. |
| **C6** | THE LIVE REGISTER ON DAY D. A pass whose stored state is `active` and whose valid days (inclusive; a null bound unbounded) contain D has live every registration with effective_day <= D and (end_day null or D < end_day); a draft, awaiting-enrolment, suspended, revoked or out-of-days pass has an EMPTY live register and keeps no car in billing. A registration effective tomorrow is not registered today; one ending today is released today. A car garage-pass has REPLACED on the pass -- at least one QR of the pass bound to it is exit only and none bound to it is still live, read from the `codes` of `show-garage-register` -- is not live: billing, whose register has no direction, does not keep it, and garage-pass still lets it out. The identity sent to billing is the identity as garage-pass recorded it, byte for byte. |
| **C7** | REGISTERS FIRST, RELEASES BY STORED FORM, NEVER BY RAW IDENTITY. Every live identity is registered through the door (idempotent there) and the stored form per garage is taken from the door's printed answer -- the connector never reimplements billing's normalisation, and a copy of the folded rule in the package is refused by a scan of the source. Then every row billing holds whose (garage, form) no live identity produced is released by passing that form back, which is sound because the normalisation is idempotent at the door. EVERY RELEASE NAMES THE ONE COVERED GARAGE THAT STORES THE FORM (`release-vehicle --garage`), so it takes that row and no other: a car swap whose two plates fold to one form at the folded garage converges in one run with the new car's row never touched -- billing answers COVERED for the new car at every garage after every door call of the run. The door's unnamed release, which fans out by identity over every covered garage, is never called. |
| **C8** | A COLLISION RELEASES NOTHING. Two live identities with one stored form at one garage are reported by name -- garage, form, both identities -- nothing is released for that link, it does not converge, and the run exits 1. |
| **C9** | THE VERDICT IS THE FINAL READ. After the run's writes both sides are read again and billing's rows, as (garage, form), are compared with every live identity's forms from the door's answers: each difference is a DIVERGENCE naming the garage, the form and the side that holds it; a pass whose live register changed under the run is named. A LIVE IDENTITY WHOSE REGISTER DID NOT COME BACK `done` -- refused, failed, or an answer the connector cannot read -- has no known form, cannot converge, AND STOPS THE LINK'S RELEASES: nothing is released for that link that run, the registers that did answer stand, the finding names the identity and what the door said, and the next run re-reads -- an incomplete picture of the desired set is never a licence to delete, and a car billing already holds keeps its rows through a door call that did not answer. A door refusal on the way -- a car held by another agreement -- is recorded on its action with the door's own sentence, a door that exited 0 with an answer the connector cannot read is recorded as `unparseable` carrying what it printed, and the final read decides either way. A REFUSED REGISTER IS NOT TRANSIENT: a car held by another agreement stays held until an operator moves it, and until then the link releases nothing on every run, loudly -- exit 1, the finding, the identity, the door's words; that is this rule holding, not a fault of the connector's. A CAR MOVING BETWEEN TWO LINKS OF ONE RUN DOES NOT WAIT FOR THE NEXT RUN: a link whose register the door refused is run once more, from fresh reads, when another link of the same run released a row after it ran, so the car the other link let go is registered and this link's releases are made in that run; its report keeps both attempts' actions and takes its findings and verdict from the second -- unless the second attempt is refused at its read (a module that did not answer, or a refusal that began between the attempts): that attempt wrote nothing, so the report is the first attempt's, NOT REFUSED, with its actions, live register, expected and billing rows, the second attempt's findings added, and the link does not converge. THE REPORT CLAIMS NOTHING THE RUN COULD NOT LEARN: a row billing holds that no known form accounts for, while some live identity's stored form is unknown, may be that identity's -- its sentence names the identities whose forms are unknown and does not call the row foreign. THE REFUSALS ARE CHECKED AGAIN ON THE FINAL READ: the registrar, the two garage sets, an unreadable record, rows outside a set, ambiguous ids -- one that fails there is named exactly as at the start of a run and the link does not converge. Every register and release the run made is in the report with its reason, and every release with the garage it named. |
| **C10** | CONVERGENCE, NOT A JOURNAL. Nothing the connector needs survives between runs -- the package writes no file and keeps no state -- so a run killed between the registers and the releases is repaired by the next run from fresh reads, and a run over a link billing already holds correctly makes no write. Two runs over one link at once are not serialised by the connector; the contract says so, and a run whose final read disagrees exits 1. |
| **C11** | REFUSE THE LINK, WRITING NOTHING. An agreement whose registrar is not `outside`, garage sets that differ (exact text, as sets), a pass or a garage stored unreadable, rows at garages outside either set, a covered set whose ids the door's printed line cannot tell apart (one id is another plus `: ` plus anything), and a module that would not answer the read -- including a WRONG TENANT on either side, which is that module's own refusal by name and never an empty register -- each stop the link before any write, by name, and the link's action list is empty. |
| **C12** | THE REPORT'S SHAPE IS PUBLISHED AND GENERATED. Its keys are derived from the dataclasses that render it and every key is present on every instance; every finding code, side, action, outcome and reason the connector emits is in the registry the contract is generated from, read from the source by AST; a key or a code the contract does not list reddens the suite. |
| **C13** | THE DOOR'S PRINTED LINE IS PINNED. The one piece of prose the connector reads -- `  at garage {garage}: {form}`, one line per garage the call reached after the first -- is matched against the garage ids the register read already named, so a form may contain anything and a line naming no known garage is reported unparseable rather than guessed at. A covered set in which one id is another id plus the separator plus anything (`g` and `g: 2`) is the one shape a line cannot be read from without guessing, and such a link is REFUSED before any write, by name; the parser's longest-first order is never asked to decide it. Measured against the pinned module, so a change there reddens this repository. |
| **C14** | NOTHING PERSONAL TRAVELS. The report carries ids, garages, days, identities and stored forms and nothing else: a holder's name, phone or address stored on the pass reaches no read the connector makes and appears nowhere in a report rendered from a real pass that carries one. |
| **C15** | THE EXIT GUARANTEE. The connector touches registrations only: its subprocess calls are exactly `show-pass`, `show-garage-register`, `show-register`, `register-vehicle` and `release-vehicle`, read from the source; it has no exit verb and no field of its report could deny one; and garage-pass's own access answer at a lane is the same before and after a run. |
| **C16** | Every fixture carries its own control asserting it holds the property it claims to represent, and those controls run as tests: the two garages of every linked fixture DIFFER in billing identity rule, and the swap plates fold to one form under the folded rule and to two under the exact rule. |
| **C17** | THE PER-GARAGE REGISTER IS COMPARED, OR IT IS NAMED. An identity live at some of the garages the link compares and not at others is a picture billing's door cannot be made to hold -- it registers a car at every covered garage or at none -- and the identity-set comparison alone would call it converged while billing covered the car at a garage the pass does not. So the run names it from the final read (`PASS_REGISTER_ASYMMETRIC`: the identity, the garages that hold it, the garages that do not), the link does not converge, exit 1; the finding is raised on the final read, after the run's own registers and releases, and causes no write of its own -- the identity the first read showed live was registered at every covered garage in step 2, as every live identity is, and the next run makes the same register and names it again; `expected` and the divergence lines are what they were. Not reachable through garage-pass's own verbs at the pinned commit; a row written past them is. |

That is 17 guarantees. Every one of them has a fail control that has been proven to fire, and the count above is derived from the registry rather than typed here.
<!-- END:guarantees -->

---

Built by 72 Knots Method by 72Knots.ai
