"""Two real databases, one per module, each migrated from its PINNED commit --
driven through the two command lines wherever a command line exists.

Not a test module (no ``test_`` prefix) and not a conftest: imported by name,
so a reader of any test can see where the databases came from.

**THE PIN IS STATED ONCE.** ``pyproject.toml``'s dev extra pins each module
to a commit; this file reads those two lines for the commits whose
``migrations/`` it applies, and ``tests/test_c3_...`` asserts the INSTALLED
packages are those commits too (their ``direct_url.json``). A pin moved in
one place and not the others is caught, not assumed.

**THE MIGRATIONS ARE FETCHED, NOT VENDORED.** Neither package ships its
``migrations/`` directory, so the harness fetches the pinned commit into
``.pins/<module>/`` (gitignored) with ``git fetch --depth 1`` and
``git archive`` -- never a checkout -- and applies the files sorted, as the
owner, exactly as each module's own harness does. Once fetched, the suite
runs offline.

**WHAT IS NOT DRIVEN THROUGH A COMMAND LINE, AND WHY.** Three things have no
verb in either module, so the harness does them the way the modules' own
test harnesses do:

- a TENANT, in either database: ``INSERT INTO tenants`` as the owner;
- billing's GARAGES, PAYER and AGREEMENT: ``monthly_billing.store.records``
  -- ``store_garage``, ``store_payer``, ``store_agreement`` -- the module's
  published store API, under the application role;
- a pass or garage stored UNREADABLE in garage-pass: a raw ``UPDATE`` as the
  owner of a timezone the system does not carry, which is the only way an
  unreadable record can exist (the module refuses to write one).

Everything else -- garage-pass's garages, passes, registrations, endings,
state changes, QRs and car replacements; billing's registrations -- goes
through the two command lines.
The CONNECTOR itself never touches any of this: it sees the two console
scripts and nothing else.

**ONE CLUSTER, ONE RUNNER.** The migrations ``CREATE`` or ``ALTER`` the
application ROLE, which is cluster-global; two runners migrating in one
cluster at once collide on it. The two modules' roles are distinct, so the
pair can be migrated in sequence in one run, under an advisory lock taken on
a shared database of the cluster, the way both modules' harnesses take it.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tomllib
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parent.parent
PINS_DIR = ROOT / ".pins"
DOCUMENTS = ROOT / "tests" / "documents"

#: The cluster DSN the harness may create databases in (superuser or a role
#: with CREATEDB and BYPASSRLS), e.g. ``host=localhost user=postgres
#: password=postgres dbname=postgres``.
CLUSTER_DSN = os.environ.get("PASS_BILLING_CONNECTOR_TEST_DSN")
APP_PASSWORD = "test-only-password"

GARAGE_PASS = "garage-pass"
MONTHLY_BILLING = "monthly-billing"
MODULES = (GARAGE_PASS, MONTHLY_BILLING)
APP_ROLE = {GARAGE_PASS: "garage_pass_app", MONTHLY_BILLING: "monthly_billing_app"}
DSN_ENV = {GARAGE_PASS: "GARAGE_PASS_DSN", MONTHLY_BILLING: "MONTHLY_BILLING_DSN"}
REPO = {m: f"https://github.com/openparking-ai-code/{m}.git" for m in MODULES}

#: 'pbc', as a bigint: one key, one meaning -- "this harness is migrating".
MIGRATION_LOCK_KEY = 0x706263

def needs_databases(test):
    """The two marks every database-driven test carries: the `needs_postgres`
    mark CI checks did not skip, and the skip itself for a machine without a
    cluster -- the one allowance in the suite, named in pyproject.toml."""
    skip = pytest.mark.skipif(not CLUSTER_DSN, reason="PASS_BILLING_CONNECTOR_TEST_DSN is not set")
    return pytest.mark.needs_postgres(skip(test))


# ------------------------------------------------------------------- the pin


def pinned_commits() -> dict[str, str]:
    """``{module: sha}`` from pyproject.toml's dev extra -- the one place."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    pins: dict[str, str] = {}
    for requirement in project["optional-dependencies"]["dev"]:
        found = re.fullmatch(
            r"openparking-(garage-pass|monthly-billing)\[store\] @ "
            r"git\+https://github\.com/openparking-ai-code/(garage-pass|monthly-billing)@([0-9a-f]{40})",
            requirement,
        )
        if found:
            assert found.group(1) == found.group(2), requirement
            pins[found.group(1)] = found.group(3)
    missing = [m for m in MODULES if m not in pins]
    assert not missing, f"pyproject.toml pins no commit for {missing}"
    return pins


def migrations_of(module: str) -> list[Path]:
    """The pinned commit's ``migrations/*.sql``, sorted, fetched on first use."""
    sha = pinned_commits()[module]
    target = PINS_DIR / module / sha
    marker = target / ".fetched"
    if not marker.exists():
        target.mkdir(parents=True, exist_ok=True)
        git = ["git", "-C", str(target)]
        subprocess.run([*git, "init", "-q"], check=True)
        subprocess.run([*git, "fetch", "-q", "--depth", "1", REPO[module], sha], check=True)
        archive = subprocess.run([*git, "archive", sha, "migrations"], check=True,
                                 capture_output=True)
        subprocess.run(["tar", "-x", "-C", str(target)], input=archive.stdout, check=True)
        marker.write_text(sha)
    files = sorted((target / "migrations").glob("*.sql"))
    assert files, f"no migration files for {module} at {sha}"
    return files


# -------------------------------------------------------------- the cluster


def _connect(dsn: str):
    import psycopg

    return psycopg.connect(dsn)


def _with_dbname(dsn: str, dbname: str, **extra: str) -> str:
    from psycopg import conninfo

    params = conninfo.conninfo_to_dict(dsn)
    params["dbname"] = dbname
    params.update(extra)
    return conninfo.make_conninfo(**params)


@contextmanager
def cluster_lock():
    """See the module docstring: taken on a shared database, per cluster."""
    import psycopg

    holder = None
    for shared in ("postgres", "template1"):
        try:
            holder = _connect(_with_dbname(CLUSTER_DSN, shared))
            break
        except psycopg.OperationalError:
            continue
    if holder is None:
        print("harness.cluster_lock: no shared database accepted the connection; the "
              "migration lock is not cluster-wide.", file=sys.stderr)
        holder = _connect(CLUSTER_DSN)
    holder.autocommit = True
    with holder.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK_KEY,))
        try:
            yield
        finally:
            cursor.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_LOCK_KEY,))
    holder.close()


@dataclass(frozen=True)
class Database:
    module: str
    name: str
    owner_dsn: str
    app_dsn: str


def create_databases(suffix: str = "test") -> dict[str, Database]:
    """Drop, create and migrate ``pbc_<module>_<suffix>`` for both modules."""
    assert CLUSTER_DSN, "PASS_BILLING_CONNECTOR_TEST_DSN is not set"
    out: dict[str, Database] = {}
    with cluster_lock():
        for module in MODULES:
            name = f"pbc_{module.replace('-', '_')}_{suffix}"
            admin = _connect(CLUSTER_DSN)
            admin.autocommit = True
            with admin.cursor() as cursor:
                cursor.execute(f"DROP DATABASE IF EXISTS {name}")
                cursor.execute(f"CREATE DATABASE {name}")
            admin.close()
            owner_dsn = _with_dbname(CLUSTER_DSN, name)
            owner = _connect(owner_dsn)
            owner.autocommit = True
            with owner.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
                for path in migrations_of(module):
                    try:
                        cursor.execute(path.read_text())
                    except Exception:
                        cursor.execute("ROLLBACK")
                        raise
                cursor.execute(f"ALTER ROLE {APP_ROLE[module]} LOGIN PASSWORD '{APP_PASSWORD}'")
            owner.close()
            app_dsn = _with_dbname(CLUSTER_DSN, name, user=APP_ROLE[module],
                                   password=APP_PASSWORD)
            out[module] = Database(module, name, owner_dsn, app_dsn)
    return out


def drop_databases(databases: dict[str, Database]) -> None:
    """Dropped at the end of the session -- after any session a failing test
    left open on them is ended, or the drop refuses with ObjectInUse."""
    admin = _connect(CLUSTER_DSN)
    admin.autocommit = True
    with admin.cursor() as cursor:
        for db in databases.values():
            cursor.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()", (db.name,))
            cursor.execute(f"DROP DATABASE IF EXISTS {db.name}")
    admin.close()


def new_tenant(db: Database) -> str:
    slug = f"t-{uuid4().hex[:12]}"
    owner = _connect(db.owner_dsn)
    owner.autocommit = True
    with owner.cursor() as cursor:
        cursor.execute("INSERT INTO tenants (slug, name) VALUES (%s, %s) RETURNING id",
                       (slug, slug))
        (tenant_id,) = cursor.fetchone()
    owner.close()
    return str(tenant_id)


# ------------------------------------------------------------- the two sides


@dataclass(frozen=True)
class Pair:
    """One test's world: a fresh tenant in each database, and the environment
    the two console scripts read their DSNs from."""

    gp: Database
    mb: Database
    gp_tenant: str
    mb_tenant: str

    @property
    def env(self) -> dict[str, str]:
        return {**os.environ, DSN_ENV[GARAGE_PASS]: self.gp.app_dsn,
                DSN_ENV[MONTHLY_BILLING]: self.mb.app_dsn}

    # -- garage-pass, through its command line ------------------------------

    def gp_run(self, *argv: str, check: bool = True) -> subprocess.CompletedProcess:
        done = subprocess.run([GARAGE_PASS, *argv, "--tenant", self.gp_tenant],
                              capture_output=True, text=True, env=self.env)
        if check:
            assert done.returncode == 0, f"garage-pass {argv}: {done.returncode}\n" \
                                         f"{done.stdout}\n{done.stderr}"
        return done

    def gp_garage(self, garage_id: str, timezone_name: str) -> None:
        document = {"id": garage_id, "timezone": timezone_name, "transient_available": True}
        self.gp_run("create-garage", "--garage", _tmp_json(document))

    def gp_pass(self, pass_id: str, garages: tuple[str, ...], *, valid_from: str | None,
                valid_to: str | None, state: str = "active") -> None:
        document = {
            "id": pass_id, "garage_ids": list(garages), "label": "Fleet",
            "holder": {"email": "holder@example.com", "name": "A Holder", "phone": None},
            "terms": {"valid_from": valid_from, "valid_to": valid_to, "windows": [],
                      "max_stay_minutes": None, "visit_allowance": None,
                      "directions": ["entry", "exit"], "allowed_lanes": None},
            "state": state,
        }
        self.gp_run("create-pass", "--garage", garages[0], "--pass", _tmp_json(document),
                    "--by", "the harness", "--at", "2026-01-01T00:00:00+00:00")

    def gp_register(self, pass_id: str, garage: str, identity: str, effective_day: str,
                    end_day: str | None = None, *, check: bool = True):
        argv = ["register-vehicle", "--garage", garage, "--pass-id", pass_id, "--vehicle",
                identity, "--effective-day", effective_day]
        if end_day:
            argv += ["--end-day", end_day]
        return self.gp_run(*argv, check=check)

    def gp_end(self, pass_id: str, garage: str, identity: str, end_day: str) -> None:
        self.gp_run("end-registration", "--garage", garage, "--pass-id", pass_id, "--vehicle",
                    identity, "--end-day", end_day)

    def gp_state(self, pass_id: str, garage: str, state: str, at: str) -> None:
        self.gp_run("set-state", "--garage", garage, "--pass-id", pass_id, "--state", state,
                    "--by", "the harness", "--reason", "the fixture", "--at", at)

    def gp_enrols_at(self, garage: str, end: str) -> None:
        self.gp_run("set-garage-enrols-at", "--garage", garage, "--enrols-at", end,
                    "--by", "the harness", "--at", "2026-01-01T00:00:00+00:00",
                    "--reason", "the fixture")

    def gp_issue_qr(self, pass_id: str, garage: str, qr: str, starts_on: str) -> str:
        """A QR for the pass, through issue-enrolment; returns its token."""
        done = self.gp_run("issue-enrolment", "--garage", garage, "--pass-id", pass_id,
                           "--enrolment-id", qr, "--starts-on", starts_on, "--days-valid", "30",
                           "--by", "the harness", "--at", f"{starts_on}T08:00:00-06:00")
        return json.loads(done.stdout)["token"]

    def gp_redeem(self, garage: str, token: str, identity: str, at: str) -> dict:
        """The lane presents the QR at an entry: the first use binds the car and
        registers it on the pass, at every garage the pass names."""
        return json.loads(self.gp_run("redeem-enrolment", "--garage", garage, "--token", token,
                                      "--vehicle", identity, "--lane", "L1", "--direction",
                                      "entry", "--at", at).stdout)

    def gp_replace_car(self, garage: str, qr: str, new_qr: str, starts_on: str) -> str:
        """replace-car: the old QR exit only, a new QR on the same pass; returns
        the new QR's token."""
        done = self.gp_run("replace-car", "--garage", garage, "--enrolment-id", qr,
                           "--new-enrolment-id", new_qr, "--starts-on", starts_on,
                           "--days-valid", "30", "--by", "the harness",
                           "--reason", "rental swapped", "--at", f"{starts_on}T08:00:00-06:00")
        return json.loads(done.stdout)["new"]["token"]

    def gp_show(self, pass_id: str, garage: str) -> dict:
        return json.loads(self.gp_run("show-pass", "--garage", garage, "--pass-id",
                                      pass_id).stdout)

    def gp_make_garage_unreadable(self, garage_id: str) -> None:
        """A raw write as the owner: the only way an unreadable garage exists."""
        owner = _connect(self.gp.owner_dsn)
        owner.autocommit = True
        with owner.cursor() as cursor:
            cursor.execute("UPDATE garages SET timezone = %s WHERE tenant_id = %s "
                           "AND external_id = %s", ("Not/AZone", self.gp_tenant, garage_id))
            assert cursor.rowcount == 1
        owner.close()

    # -- monthly-billing: the store API for what has no verb, the command
    #    line for everything that has one ---------------------------------

    def mb_run(self, *argv: str, check: bool = True) -> subprocess.CompletedProcess:
        done = subprocess.run([MONTHLY_BILLING, *argv, "--tenant", self.mb_tenant],
                              capture_output=True, text=True, env=self.env)
        if check:
            assert done.returncode == 0, f"monthly-billing {argv}: {done.returncode}\n" \
                                         f"{done.stdout}\n{done.stderr}"
        return done

    def mb_seed(self, garages: tuple[dict, ...], agreements: tuple[dict, ...]) -> None:
        """Garages first, then every payer the agreements name, then the
        agreements -- each homed at a garage seeded now or by an earlier call
        on this pair (`_SEEDED` remembers them; a payer seeded twice would be
        a unique violation, so payers are remembered too)."""
        from monthly_billing.agreement import load_agreement
        from monthly_billing.cli import load_garage_file
        from monthly_billing.store.postgres import tenant
        from monthly_billing.store.records import store_agreement, store_garage, store_payer

        known = _SEEDED.setdefault(self.mb_tenant, {"garages": {}, "payers": {}})
        loaded_agreements = [load_agreement(a) for a in agreements]
        app = _connect(self.mb.app_dsn)
        app.autocommit = False
        try:
            with tenant(app, self.mb_tenant) as cursor:
                for document in garages:
                    garage = load_garage_file(_tmp_json(document))
                    known["garages"][garage.id] = (garage, store_garage(cursor, self.mb_tenant,
                                                                        garage))
                for agreement in loaded_agreements:
                    if agreement.payer_id not in known["payers"]:
                        known["payers"][agreement.payer_id] = store_payer(
                            cursor, self.mb_tenant, agreement.payer_id,
                            f"Payer {agreement.payer_id}")
                    home, home_uuid = known["garages"][agreement.garage_id]
                    store_agreement(cursor, self.mb_tenant, home, home_uuid,
                                    known["payers"][agreement.payer_id], agreement,
                                    now=datetime(2026, 3, 1, tzinfo=UTC))
            app.commit()
        finally:
            app.close()

    def mb_revise(self, agreement: dict) -> None:
        """A NEW VERSION of an agreement this pair seeded -- the store API, as
        `mb_seed`, since versioning an agreement has no verb. What a test uses
        to move the covered set UNDER a run (C9): billing's own operator
        storing version 2 between the connector's reads."""
        from monthly_billing.agreement import load_agreement
        from monthly_billing.store.postgres import tenant
        from monthly_billing.store.records import store_agreement

        known = _SEEDED[self.mb_tenant]
        loaded = load_agreement(agreement)
        app = _connect(self.mb.app_dsn)
        app.autocommit = False
        try:
            with tenant(app, self.mb_tenant) as cursor:
                home, home_uuid = known["garages"][loaded.garage_id]
                store_agreement(cursor, self.mb_tenant, home, home_uuid,
                                known["payers"][loaded.payer_id], loaded,
                                now=datetime(2026, 9, 1, tzinfo=UTC))
            app.commit()
        finally:
            app.close()

    def mb_register(self, agreement: str, identity: str, at: str | None = None, *,
                    check: bool = True):
        argv = ["register-vehicle", "--agreement", agreement, "--vehicle", identity]
        if at:
            argv += ["--at", at]
        return self.mb_run(*argv, check=check)

    def mb_release(self, agreement: str, identity: str, *, check: bool = True):
        return self.mb_run("release-vehicle", "--agreement", agreement, "--vehicle", identity,
                           check=check)

    def mb_rows(self, agreement: str) -> set[tuple[str, str]]:
        register = json.loads(self.mb_run("show-register", "--agreement", agreement).stdout)
        return {(r["garage"], r["identity_normalised"]) for r in register["registrations"]}

    # -- the connector ------------------------------------------------------

    def link(self, pass_id: str = "pass-1", pass_garage: str = "garage-a",
             agreement_id: str = "ag-1", **overrides: str) -> dict:
        link = {"pass_tenant": self.gp_tenant, "pass_id": pass_id, "pass_garage": pass_garage,
                "billing_tenant": self.mb_tenant, "agreement_id": agreement_id}
        link.update(overrides)
        return link

    def sync(self, links: list[dict], at: str, *, monkeypatch) -> tuple[int, dict]:
        """Run the connector IN-PROCESS with the two DSNs in its environment --
        the environment its subprocesses inherit. Returns (exit, report)."""
        import io
        from contextlib import redirect_stdout

        from pass_billing_connector.cli import main

        for key, value in self.env.items():
            if key in DSN_ENV.values():
                monkeypatch.setenv(key, value)
        path = _tmp_json({"links": links})
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["sync", "--links", path, "--at", at])
        return code, json.loads(out.getvalue())

    def sync_script(self, links: list[dict], at: str) -> tuple[int, dict, str]:
        """The console script itself, as a subprocess."""
        path = _tmp_json({"links": links})
        done = subprocess.run(["pass-billing-connector", "sync", "--links", path, "--at", at],
                              capture_output=True, text=True, env=self.env)
        report = json.loads(done.stdout) if done.stdout.strip() else {}
        return done.returncode, report, done.stderr


#: What each pair has seeded into billing, by tenant: see Pair.mb_seed.
_SEEDED: dict[str, dict[str, dict]] = {}


def _tmp_json(document: dict) -> str:
    import tempfile

    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(document, handle)
    handle.close()
    return handle.name


# ---------------------------------------------------------------- documents


def mb_garage(garage_id: str, timezone_name: str, rule: str, currency: str = "USD") -> dict:
    return {"id": garage_id, "timezone": timezone_name, "currency": currency,
            "billing_day": "last_day_of_month", "payment_grace_days": 5, "identity_rule": rule}


def mb_agreement(agreement_id: str, home: str, covered: tuple[str, ...], *,
                 payer: str = "payer-1", registrar: str = "outside") -> dict:
    return {
        "id": agreement_id, "version": 1, "garage_id": home, "covered_garage_ids": list(covered),
        "payer_id": payer, "spots": 4, "registrar": registrar,
        # The module refuses an empty list it writes itself; an outside
        # registrar's list is refused unless empty (its G42).
        "vehicles": [] if registrar == "outside" else ["OWN-1"],
        "monthly_price_minor": 48000, "start_day": "2026-03-10",
        "mandate": {
            "agreed_by": "the fleet manager", "agreed_at_iso": "2026-03-09T16:20:00-07:00",
            "terms_shown": "A recurring monthly charge for monthly parking.",
            "frequency_shown": "Monthly, on the last day of each month.",
            "amount_basis_shown": "The stated monthly price.",
            "cancellation_shown": "Cancel in writing; the paid period runs to its end.",
        },
    }


#: THE TWO GARAGES OF EVERY LINKED FIXTURE, AND THE AXIS THAT DECIDES: their
#: billing identity rules DIFFER. tests/test_fixture_axes.py holds the control.
GARAGE_A = ("garage-a", "America/Denver", "folded_alphanumeric")
GARAGE_B = ("garage-b", "Europe/Berlin", "exact")

#: A day inside every fixture pass's valid days, and the instant on it.
DAY = "2026-09-16"
AT = "2026-09-16T09:00:00-06:00"


def standard_world(pair: Pair, *, pass_state: str = "active", valid_from: str | None = "2026-01-01",
                   valid_to: str | None = "2026-12-31", registrar: str = "outside",
                   covered: tuple[str, ...] = ("garage-a", "garage-b"),
                   pass_garages: tuple[str, ...] = ("garage-a", "garage-b")) -> None:
    """A pass over garage-a and garage-b, linked to ag-1 covering the same two."""
    for garage_id, zone, _rule in (GARAGE_A, GARAGE_B):
        pair.gp_garage(garage_id, zone)
    pair.gp_pass("pass-1", pass_garages, valid_from=valid_from, valid_to=valid_to,
                 state=pass_state)
    pair.mb_seed(
        tuple(mb_garage(g, z, r) for g, z, r in (GARAGE_A, GARAGE_B)),
        (mb_agreement("ag-1", "garage-a", covered, registrar=registrar),),
    )
