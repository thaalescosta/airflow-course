"""The course's primary correctness artifact, and the onboarding gate.

One command, from the repository root:

    .venv/Scripts/python tests/assert_pipeline_kpis.py

It walks the six onboarding steps in the order the spec fixes - environment up,
Cosmos importable, dbt executable, data source reachable, a first DAG parsing,
this assertion green - demonstrating each one rather than asserting it, and then
does the one thing the whole course exists to be able to do:

    run the nightly pipeline twice over a known date range, and check the daily
    KPI table in the warehouse against values computed from the source, without
    consulting a single dbt model.

Why the expectation is not SQL. If the expected numbers were produced by
running the models, the assertion would be comparing the models to themselves
and could only ever fail for a reason that does not matter - a renamed column,
a schema that moved. The expectation here is a second, independent
implementation of the same business rules: an HTTP client that walks the frozen
API's pagination envelope, and plain Python that adds up integers. When the two
disagree, one of them is wrong, and the disagreement is the finding.

Three more properties this file is built to have:

* **It reads state, not code.** The only thing asserted about the pipeline is
  what is in the warehouse and what Airflow reports about the run it triggered.
  Nothing here imports a pipeline module, reads a DAG file, or looks for a
  string in a source file. That is the rule from the spec's Testing Decisions,
  and `tests/test_orders_ingestion.py` is the seam it does not apply to.
* **It is deterministic.** The source is frozen (ADR 0005) and the warehouse is
  rebuilt from it on every run, so the same command gives the same answer, and
  the printed `kpi_digest` is the evidence: same digest, same numbers.
* **It is idempotent to assert, not merely to claim.** The pipeline is run
  twice over the same window and the second result must equal the first. An
  extraction that appended instead of upserting, or a model that accumulated,
  would double the rows and fail here rather than in production.

The one place this file looks at something other than the warehouse is the DAG
run's task instances, because "Cosmos rendered the dbt project into tasks" is
one of the things a single pass is specified to exercise and the rendered graph
is the only place it is observable. It reads the graph Airflow reports for a
run it triggered; it never reads Cosmos's source or the DAG file.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, localcontext
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import psycopg2

# --------------------------------------------------------------------------
# What is being asserted, stated once so there is nothing to keep in sync with
# the models except the column list below.
# --------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]

AIRFLOW_API = "http://localhost:8080"

# The course warehouse, reached on its published host port rather than through
# Airflow. This process is outside the stack, so it has no Execution API to
# resolve the `warehouse_default` connection through, and reading the local
# secret file is the honest host-side equivalent of what the CLI did when the
# connection was seeded.
WAREHOUSE_SECRET = REPO_ROOT / ".secrets" / "warehouse_pg_password"
WAREHOUSE = {
    "host": "127.0.0.1",
    "port": 5433,
    "dbname": "warehouse",
    "user": "warehouse",
}

# The orders API, reached over HTTP from outside the stack. The *pipeline* reads
# it as http://orders-api:8000 over the container network, by service name; the
# gate below proves that separately, in the container. Two transports for one
# frozen source is the point: the expectation must not depend on the same path
# the thing under test depends on.
ORDERS_API_HOST_URL = "http://127.0.0.1:8010"

NIGHTLY_DAG_ID = "pipeline_nightly_order_kpis"

# The course's DAG set, stated here rather than inferred from the `dags/`
# directory. This is the one place the assertion claims the course has a single
# pipeline, and it makes the claim from Airflow's own report of what parsed
# rather than from a directory listing, so it is still the primary seam's rule:
# read the state, not the source.
#
# Two DAGs used to be here that are not now, and their absence is the reason this
# list is asserted rather than merely printed. `pipeline_orders_ingestion`
# carried a second copy of the extraction task, on the same nightly timetable,
# writing to the same `public.orders` — a second writer that was inert only
# while paused, and "paused" is a row in a local metadata database that a fresh
# clone does not inherit. `pipeline_dbt_transform` carried a second Cosmos task
# group with the same `group_id` over the same dbt models. A second writer to one
# table is silent when it is idempotent, which is precisely why it needed to be
# removed rather than left paused.
#
# To add a DAG, add it here with a reason. A new scheduled DAG fails gate 5
# until it is registered, because two scheduled DAGs is the state this assertion
# exists to rule out.
EXPECTED_DAGS = {
    # The continuous project: the one pipeline, and the only scheduled DAG.
    NIGHTLY_DAG_ID: "the nightly pipeline under assertion",
    # A connection probe, schedule=None, on its own health-check table.
    "pipeline_warehouse_connection_check": "the warehouse connection probe",
}

# The window under assertion. Chosen, not arbitrary:
#
#   * It spans 1116 orders, so at the extraction's page size of 1000 the API's
#     pagination is walked for real. A window small enough to fit in one page
#     would leave the envelope untested and the assertion weaker than it reads.
#   * It is a strict subset of the source's world in both directions. Orders
#     exist on both sides of it, so if the DAG dropped a bound, or sent the
#     window unreduced, days outside it would appear in the warehouse and the
#     assertion would say so.
#   * Both ends are midnight UTC on a day the source generates orders for, so
#     the half-open bounds are exercised at the boundary rather than in the
#     middle of a day.
WINDOW_AFTER = "2026-02-01T00:00:00Z"
WINDOW_BEFORE = "2026-06-15T00:00:00Z"

FACT_RELATION = "analytics_marts.fct_daily_order_kpis"
RAW_RELATION = "public.orders"

# The dbt models the pipeline is specified to materialise, in layer order. Used
# to check that Cosmos rendered each of them into a task of the run that produced
# the table being compared.
DBT_MODELS = (
    "stg_orders",
    "stg_order_items",
    "int_orders_enriched",
    "fct_daily_order_kpis",
)

# A page size the extraction does not use. If both clients walked pages the same
# way over the same boundaries, a shared mistake about how to page would cancel
# out. Different boundaries, same rows, is the check.
EXPECTATION_PAGE_SIZE = 500

KPI_COLUMNS = (
    "orders_total",
    "customers_total",
    "units_total",
    "line_items_total",
    "gross_merchandise_cents",
    "net_orders",
    "net_merchandise_cents",
    "cancelled_orders",
    "returned_orders",
    "net_average_order_value_cents",
)

# The pipeline's one business rule, restated here independently of
# dags/dbt/models/intermediate/int_orders_enriched.sql, which is where the
# pipeline itself states it. Two statements of one rule in two languages is the
# price of an independent expectation; a disagreement between them is a finding
# about the rule, not about the arithmetic.
REVERSED_STATUSES = ("cancelled", "returned")

RUN_TIMEOUT_SECONDS = 900
POLL_INTERVAL_SECONDS = 5


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


class GateFailure(RuntimeError):
    """A step of the onboarding gate did not hold. Always carries a fix."""


def rule(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def show(label: str, value: Any) -> None:
    print(f"  {label:<34} {value}")


def docker(*arguments: str) -> str:
    """Run a docker command, returning stdout or raising with its stderr.

    `MSYS_NO_PATHCONV=1` matters on git-bash, which otherwise rewrites any
    argument that looks like an absolute POSIX path into a Windows path before
    the command ever reaches Docker.
    """
    completed = subprocess.run(
        ["docker", *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**__import__("os").environ, "MSYS_NO_PATHCONV": "1"},
    )
    if completed.returncode != 0:
        raise GateFailure(
            f"`docker {' '.join(arguments)}` failed:\n{completed.stderr.strip()}"
        )
    return completed.stdout


def compose_container(service: str) -> str:
    """The running container id for a compose service, by label.

    Matched on the compose service label rather than on the container name,
    because Astro puts the project name and a path hash in container names and
    the hash changes when the repository is cloned somewhere else.
    """
    found = docker(
        "ps",
        "--filter",
        f"label=com.docker.compose.service={service}",
        "--format",
        "{{.ID}}",
    ).split()
    if not found:
        raise GateFailure(
            f"No running container for compose service {service!r}. "
            "Bring the stack up with `astro dev start --no-browser --wait 5m`."
        )
    return found[0]


def exec_in(service: str, script: str) -> str:
    return docker("exec", compose_container(service), "python", "-c", script)


# --------------------------------------------------------------------------
# Gate step 1 - the environment is up
# --------------------------------------------------------------------------


def gate_environment_up() -> None:
    rule("Gate 1/6  Environment up")

    engine = docker("info", "--format", "{{.ServerVersion}}").strip()
    show("docker engine", engine)

    expected_services = (
        "postgres",
        "warehouse-postgres",
        "orders-api",
        "scheduler",
        "dag-processor",
        "api-server",
        "triggerer",
    )
    for service in expected_services:
        container = compose_container(service)
        state = docker(
            "inspect", container, "--format", "{{.State.Status}}"
        ).strip()
        if state != "running":
            raise GateFailure(
                f"Compose service {service!r} is {state!r}, not running. "
                "Run `astro dev start --no-browser --wait 5m`."
            )
    show("running compose services", ", ".join(expected_services))

    # The monitor endpoint, not a plain /health: the api-server's own liveness
    # route says nothing about whether the components this assertion depends on
    # - scheduler, dag-processor, triggerer - are actually heartbeating.
    health = api_get("/api/v2/monitor/health")
    for component in ("metadatabase", "scheduler", "dag_processor", "triggerer"):
        status = health.get(component, {}).get("status")
        if status != "healthy":
            raise GateFailure(f"{component} is {status!r}, not healthy.")
    show("airflow components", ", ".join(sorted(health)))

    if not WAREHOUSE_SECRET.exists():
        raise GateFailure(
            f"{WAREHOUSE_SECRET} does not exist. It is gitignored and has to be "
            "created once per machine; see reference/environment-baseline.md §7."
        )
    # The secret is read as bytes and stripped of a trailing newline, because a
    # file written by a Windows editor arrives with CRLF and Postgres takes the
    # password from this file verbatim. A stray CR here is a password that no
    # other client can reproduce, and it fails as "password authentication
    # failed" several steps away from its cause.
    password = WAREHOUSE_SECRET.read_bytes().strip()
    show("warehouse secret", f"{WAREHOUSE_SECRET.name} ({len(password)} bytes, read)")

    connections = api_get("/api/v2/connections?limit=1000")
    connection_ids = {row["connection_id"] for row in connections.get("connections", [])}
    if "warehouse_default" not in connection_ids:
        raise GateFailure(
            "The Airflow connection `warehouse_default` is not seeded, so no task "
            "can reach the warehouse. Seed it once per stack, out of band:\n"
            "  docker exec <api-server> airflow connections add warehouse_default \\\n"
            "    --conn-type postgres --conn-host warehouse-postgres --conn-port 5432 \\\n"
            "    --conn-schema warehouse --conn-login warehouse \\\n"
            "    --conn-password \"$(cat .secrets/warehouse_pg_password)\""
        )
    show("airflow connections", ", ".join(sorted(connection_ids)))


# --------------------------------------------------------------------------
# Gate step 2 - Cosmos is importable where DAGs are parsed
# --------------------------------------------------------------------------


def gate_cosmos_importable() -> None:
    rule("Gate 2/6  Cosmos importable")

    # Checked in the dag-processor, not on the host: that is the component that
    # imports Cosmos to turn the dbt project into tasks, so an import that
    # succeeded here and failed there would be a false negative this gate exists
    # to avoid. The host venv is not the pipeline's environment.
    output = exec_in(
        "dag-processor",
        "import cosmos, sys; print(cosmos.__version__, sys.version.split()[0])",
    ).strip()
    version, python = output.split()
    show("component", "dag-processor")
    show("import cosmos", f"{version} (python {python})")

    from_requirements = (
        REPO_ROOT / "requirements.txt"
    ).read_text(encoding="utf-8")
    if f"astronomer-cosmos=={version}" not in from_requirements:
        raise GateFailure(
            f"requirements.txt does not pin astronomer-cosmos=={version}. ADR 0004 "
            "requires the running version to be the pinned one."
        )
    show("pinned in requirements.txt", f"astronomer-cosmos=={version}")


# --------------------------------------------------------------------------
# Gate step 3 - dbt is executable where tasks run
# --------------------------------------------------------------------------


def gate_dbt_executable() -> None:
    rule("Gate 3/6  dbt executable")

    # Checked in the scheduler because that is where LOCAL execution mode runs
    # each `dbt run --select ...` subprocess, by shell. A dbt that is importable
    # but not on PATH would pass a python -c check and fail every model task.
    completed = subprocess.run(
        ["docker", "exec", compose_container("scheduler"), "dbt", "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**__import__("os").environ, "MSYS_NO_PATHCONV": "1"},
    )
    if completed.returncode != 0:
        raise GateFailure(
            "`dbt --version` failed inside the scheduler:\n"
            f"{completed.stderr.strip()}"
        )
    core = next(
        line.split(":", 1)[1].strip()
        for line in completed.stdout.splitlines()
        if "installed" in line
    )
    show("component", "scheduler")
    show("dbt --version (core)", core)
    show("dbt --version (postgres)", completed.stdout.split("postgres:")[1].split("-")[0].strip())

    pinned = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    if f"dbt-core=={core}" not in pinned:
        raise GateFailure(
            f"requirements.txt does not pin dbt-core=={core}. ADR 0004 requires it."
        )
    show("pinned in requirements.txt", f"dbt-core=={core}")


# --------------------------------------------------------------------------
# Gate step 4 - the data source is reachable, by service name, over the network
# --------------------------------------------------------------------------


def gate_data_source_reachable() -> None:
    rule("Gate 4/6  Data source reachable")

    # Deliberately executed inside the Airflow network rather than from this
    # process. `dags/pipeline/nightly_order_kpis.py` reaches the API as
    # http://orders-api:8000, and the whole point of ADR 0005's second
    # consequence is that services address each other by name. Proving that from
    # the host, over a published port, would prove something else.
    script = (
        "import json, socket, urllib.request;"
        "address = socket.gethostbyname('orders-api');"
        "health = json.load(urllib.request.urlopen('http://orders-api:8000/health', timeout=5));"
        "print(address, json.dumps(health))"
    )
    output = exec_in("scheduler", script).strip()
    address, health = output.split(" ", 1)
    show("component", "scheduler")
    show("DNS orders-api", address)
    show("GET orders-api:8000/health", health)

    if '"status": "ok"' not in health:
        raise GateFailure(f"The orders API is not healthy: {health}")

    show("published for host clients", ORDERS_API_HOST_URL)


# --------------------------------------------------------------------------
# Gate step 5 - the DAGs parse, and there is exactly one pipeline
# --------------------------------------------------------------------------


def gate_one_pipeline_parses() -> None:
    rule("Gate 5/6  One pipeline, parsed")

    import_errors = api_get("/api/v2/importErrors")
    count = import_errors.get("total_entries", len(import_errors.get("import_errors", [])))
    if count:
        details = "\n".join(
            f"  {row.get('filename')}: {row.get('stack_trace', '').splitlines()[-1]}"
            for row in import_errors["import_errors"]
        )
        raise GateFailure(f"{count} DAG file(s) failed to import:\n{details}")
    show("import errors", "0")

    # The course has one pipeline. Read from the live bundle rather than from the
    # `dags/` directory: the API resolves DAGs by parsing the files, so a DAG
    # deleted from git but still registered in the metadatabase does not appear
    # here — which is what `airflow dags list` will tell you, and why that CLI
    # and the UI disagree (see reference/environment-baseline.md §7).
    parsed = api_get("/api/v2/dags?limit=100")
    found = {row["dag_id"]: row for row in parsed.get("dags", [])}
    show("dags parsed", len(found))

    unexpected = sorted(set(found) - set(EXPECTED_DAGS))
    missing = sorted(set(EXPECTED_DAGS) - set(found))
    if unexpected or missing:
        problems = []
        for dag_id in unexpected:
            row = found[dag_id]
            scheduled = row.get("timetable_summary")
            problems.append(
                f"  unexpected  {dag_id}"
                + (f"  (scheduled: {scheduled})" if scheduled else "  (unscheduled)")
                + f"  <- {row.get('fileloc', '?')}"
            )
        for dag_id in missing:
            problems.append(f"  missing      {dag_id}")
        raise GateFailure(
            "The course's DAG set is not the one this assertion expects:\n"
            + "\n".join(problems)
            + "\n\nA DAG that is not on this list is either a second writer to the "
            "pipeline's tables, a second scheduler for the dbt project, or a "
            "half-finished file. The first two are silent when they are "
            "idempotent, which is why they are ruled out here rather than left "
            "paused.\nIf the DAG is meant to exist, register it in EXPECTED_DAGS "
            "in this file with a reason next to it."
        )
    for dag_id, why in EXPECTED_DAGS.items():
        when = "scheduled" if found[dag_id].get("timetable_summary") else "on demand"
        print(f"      {when:<10}{dag_id}  ({why})")

    # Exactly one timetable in the bundle. This is the load-bearing half of the
    # check above: a second scheduled DAG is a second nightly run competing for
    # the same warehouse, whether or not it happens to be paused right now.
    scheduled = sorted(
        dag_id for dag_id, row in found.items() if row.get("timetable_summary")
    )
    if scheduled != [NIGHTLY_DAG_ID]:
        raise GateFailure(
            f"Expected exactly one scheduled DAG ({NIGHTLY_DAG_ID}), found: "
            f"{', '.join(scheduled) or 'none'}. Two DAGs on a schedule means two "
            "writers racing for the same tables."
        )
    show("scheduled DAGs", "1  (the pipeline, and nothing else)")

    dag = found[NIGHTLY_DAG_ID]
    show("dag", f"{dag['dag_id']}  ({dag.get('fileloc', '?')})")
    # `schedule` is null for a timetable-backed DAG in Airflow 3; the cron it was
    # built from is reported separately as a summary.
    schedule = dag.get("schedule") or {}
    show(
        "schedule",
        str(schedule.get("value") if schedule else dag.get("timetable_summary")),
    )

    # The rendered graph. Reported, not asserted - but asserted a step later,
    # for the run this assertion triggers. Listing it here is what makes Cosmos's
    # rendering visible rather than inferred.
    tasks = api_get(f"/api/v2/dags/{NIGHTLY_DAG_ID}/tasks")
    task_ids = sorted(row["task_id"] for row in tasks["tasks"])
    show("rendered tasks", len(task_ids))
    for task_id in task_ids:
        marker = "Cosmos " if task_id.startswith("cosmos_dbt_project.") else "hand   "
        print(f"      {marker} {task_id}")

    if dag.get("is_paused"):
        raise GateFailure(
            f"{NIGHTLY_DAG_ID} is paused. The local stack parses every DAG paused, "
            "and a triggered run of a paused DAG stays `queued` forever: nothing "
            "schedules it. Unpause it once, then run this again:\n"
            f"  curl -X PATCH '{AIRFLOW_API}/api/v2/dags/{NIGHTLY_DAG_ID}"
            "?update_mask=is_paused' -H \"Authorization: Bearer $(curl -s "
            f"{AIRFLOW_API}/auth/token | python -c "
            "\"import sys,json;print(json.load(sys.stdin)['access_token'])\")\" "
            "-H 'Content-Type: application/json' -d '{\"is_paused\": false}'\n"
            "or click DAGs -> pipeline_nightly_order_kpis -> the Pause button."
        )
    show("paused", "no")


# --------------------------------------------------------------------------
# The Airflow REST client
# --------------------------------------------------------------------------

_TOKEN: str | None = None


def api_get(path: str) -> dict[str, Any]:
    return api_request("GET", path)


def api_request(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    global _TOKEN
    if _TOKEN is None:
        # `GET /auth/token` mints a token with no credentials, and only because
        # the local stack sets `simple_auth_manager_all_admins`. That is a local
        # development convenience, not a production authentication method, and
        # it is why this file hard-codes no password: there is none to hard-code.
        response = urllib.request.urlopen(f"{AIRFLOW_API}/auth/token", timeout=30)
        _TOKEN = json.load(response)["access_token"]

    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        f"{AIRFLOW_API}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise GateFailure(
            f"{method} {path} returned {error.code}: {error.read().decode()[:400]}"
        ) from error


# --------------------------------------------------------------------------
# The independent expectation
# --------------------------------------------------------------------------


def fetch_window_orders() -> tuple[list[dict[str, Any]], dict[str, Any], int]:
    """Every order in the window, plus the first page's metadata and page count.

    A deliberately separate implementation from the extraction's: its own HTTP
    client, its own page size, and no shared code. The one thing it insists on
    is the envelope's own `total_items`, which is defined to be independent of
    the page asked for. If the walk lost a page or double-counted one, the count
    would not reconcile.
    """
    orders: list[dict[str, Any]] = []
    first_meta: dict[str, Any] | None = None
    pages = 0
    page = 1
    after: datetime | None = None
    before: datetime | None = None

    while True:
        query = urlencode(
            {
                "created_after": WINDOW_AFTER,
                "created_before": WINDOW_BEFORE,
                "page": page,
                "page_size": EXPECTATION_PAGE_SIZE,
            }
        )
        with urllib.request.urlopen(
            f"{ORDERS_API_HOST_URL}/orders?{query}", timeout=60
        ) as response:
            payload = json.load(response)

        meta = payload["meta"]
        if first_meta is None:
            first_meta = meta
            after = datetime.fromisoformat(
                payload["query"]["created_after"].replace("Z", "+00:00")
            )
            before = datetime.fromisoformat(
                payload["query"]["created_before"].replace("Z", "+00:00")
            )
        elif meta["total_items"] != first_meta["total_items"]:
            raise GateFailure(
                f"The source's total_items changed between pages "
                f"({first_meta['total_items']} then {meta['total_items']}), so the "
                "filtered result set is not stable and no pagination contract "
                "can be implemented against it."
            )
        orders.extend(payload["data"])
        pages += 1

        if not meta["has_next"]:
            break
        page = meta["next_page"]

    assert first_meta is not None
    if len(orders) != first_meta["total_items"]:
        raise GateFailure(
            f"The walk collected {len(orders)} rows but the source reported "
            f"{first_meta['total_items']} for this window."
        )
    if not (after is not None and before is not None):
        raise GateFailure("The source did not echo the window it was asked for.")
    return orders, first_meta, pages


def business_date(instant: str) -> date:
    """The UTC calendar date of an RFC 3339 instant.

    UTC explicitly, matching the models' `at time zone 'utc'`. A local date here
    would be a silent, machine-dependent disagreement with the warehouse rather
    than a failure.
    """
    return datetime.fromisoformat(instant.replace("Z", "+00:00")).astimezone(
        timezone.utc
    ).date()


def round_half_up(numerator: int, denominator: int) -> int | None:
    """Postgres `round(numeric)` in Python, or None when there is nothing to average.

    Postgres rounds halves away from zero on numeric; Decimal's ROUND_HALF_UP
    rounds halves away from zero too. The division runs at 40 significant digits,
    far more than any of these values needs, so the rounding decision is decided
    by the quotient and not by either implementation's precision.
    """
    if denominator <= 0:
        return None
    with localcontext() as context:
        context.prec = 40
        quotient = Decimal(numerator) / Decimal(denominator)
        return int(quotient.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def expected_daily_kpis() -> tuple[dict[date, dict[str, Any]], dict[str, Any], int]:
    """Daily KPIs computed from the source, in Python, with no SQL involved."""
    orders, meta, pages = fetch_window_orders()

    days: dict[date, dict[str, Any]] = {}
    for order in orders:
        day = business_date(order["created_at"])
        if not (
            datetime.fromisoformat(WINDOW_AFTER.replace("Z", "+00:00")).astimezone(
                timezone.utc
            ).date()
            <= day
            < datetime.fromisoformat(WINDOW_BEFORE.replace("Z", "+00:00"))
            .astimezone(timezone.utc)
            .date()
        ):
            raise GateFailure(
                f"The source returned {order['order_id']} created on {day}, outside "
                f"the requested window [{WINDOW_AFTER}, {WINDOW_BEFORE})."
            )
        bucket = days.setdefault(
            day,
            {
                "orders_total": 0,
                "customers": set(),
                "units_total": 0,
                "line_items_total": 0,
                "gross_merchandise_cents": 0,
                "net_merchandise_cents": 0,
                "cancelled_orders": 0,
                "returned_orders": 0,
            },
        )
        bucket["orders_total"] += 1
        bucket["customers"].add(order["customer_id"])
        bucket["units_total"] += sum(item["quantity"] for item in order["items"])
        bucket["line_items_total"] += len(order["items"])
        bucket["gross_merchandise_cents"] += order["total_cents"]
        if order["status"] in REVERSED_STATUSES:
            bucket[f"{order['status']}_orders"] += 1
        else:
            bucket["net_merchandise_cents"] += order["total_cents"]

    kpis: dict[date, dict[str, Any]] = {}
    for day, bucket in days.items():
        net_orders = (
            bucket["orders_total"]
            - bucket["cancelled_orders"]
            - bucket["returned_orders"]
        )
        kpis[day] = {
            "orders_total": bucket["orders_total"],
            "customers_total": len(bucket["customers"]),
            "units_total": bucket["units_total"],
            "line_items_total": bucket["line_items_total"],
            "gross_merchandise_cents": bucket["gross_merchandise_cents"],
            "net_orders": net_orders,
            "net_merchandise_cents": bucket["net_merchandise_cents"],
            "cancelled_orders": bucket["cancelled_orders"],
            "returned_orders": bucket["returned_orders"],
            "net_average_order_value_cents": round_half_up(
                bucket["net_merchandise_cents"], net_orders
            ),
        }
    return kpis, meta, pages


# --------------------------------------------------------------------------
# The warehouse
# --------------------------------------------------------------------------


def connect():
    password = WAREHOUSE_SECRET.read_bytes().strip().decode("utf-8")
    return psycopg2.connect(password=password, **WAREHOUSE)


def prepare_warehouse() -> None:
    """Start from an empty extract table, and say so.

    The extract table is dropped rather than truncated, because the pipeline
    recreates it (`CREATE TABLE IF NOT EXISTS` in `dags/pipeline/orders_extract.py`)
    and a drop also works on a warehouse where it has never existed. Truncating
    would leave the assertion's meaning dependent on what a previous run left
    behind.

    Dropping first is what makes "the mart contains no day outside the window" a
    statement about the pipeline rather than about the warehouse's prior contents.
    It is also why the assertion can be run twice in a row and mean the same thing
    both times.
    """
    with connect() as database, database.cursor() as cursor:
        cursor.execute(f"DROP TABLE IF EXISTS {RAW_RELATION}")
    print(f"  {'dropped':<34} {RAW_RELATION} (the pipeline recreates it)")


def read_fact_table() -> dict[date, dict[str, Any]]:
    columns = ", ".join(("order_date", *KPI_COLUMNS))
    with connect() as database, database.cursor() as cursor:
        cursor.execute(f"select {columns} from {FACT_RELATION} order by order_date")
        rows = cursor.fetchall()
    return {row[0]: dict(zip(KPI_COLUMNS, row[1:])) for row in rows}


def read_raw_counts() -> dict[str, int]:
    with connect() as database, database.cursor() as cursor:
        cursor.execute(
            "select count(*), count(distinct order_id), coalesce(max(version), 0) "
            f"from {RAW_RELATION}"
        )
        total, distinct, highest_version = cursor.fetchone()
    return {
        "rows": total,
        "distinct_order_ids": distinct,
        "max_version": highest_version,
    }


# --------------------------------------------------------------------------
# Running the pipeline
# --------------------------------------------------------------------------


def run_logical_date() -> str:
    """A logical date unique to this invocation.

    Airflow requires one (the API rejects a run without it) and treats
    `(dag_id, logical_date)` as unique, so two runs of the same DAG cannot share
    one. The assertion therefore does not label its runs with the window's start
    date: the learner may have triggered a run at that date by hand, or run this
    command twice, and either would end in a 409 that has nothing to do with
    whether the pipeline is correct.

    Labelling by the current instant is also the honest thing to do, because the
    window under test travels in the run configuration and not in the logical
    date. `check_extraction_report` reads back what the run says it extracted to
    prove the configuration is what selected the data. The two runs then differ
    in exactly the one thing that does not select rows: their labels.
    """
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def trigger_and_wait(label: str) -> str:
    logical_date = run_logical_date()
    run_id = f"kpi_assertion__{label}__{logical_date.replace(':', '').replace('-', '')}"
    api_request(
        "POST",
        f"/api/v2/dags/{NIGHTLY_DAG_ID}/dagRuns",
        {
            "dag_run_id": run_id,
            "logical_date": logical_date,
            "conf": {
                "created_after": WINDOW_AFTER,
                "created_before": WINDOW_BEFORE,
            },
            "note": "Triggered by tests/assert_pipeline_kpis.py",
        },
    )
    print(f"  {'triggered':<34} {run_id}")

    deadline = time.monotonic() + RUN_TIMEOUT_SECONDS
    state = "queued"
    run: dict[str, Any] = {}
    while time.monotonic() < deadline:
        run = api_get(f"/api/v2/dags/{NIGHTLY_DAG_ID}/dagRuns/{run_id}")
        state = run["state"]
        if state in {"success", "failed"}:
            break
        time.sleep(POLL_INTERVAL_SECONDS)

    if state != "success":
        raise GateFailure(
            f"The pipeline run {run_id} finished {state!r}, so there is nothing in "
            "the warehouse to assert about.\n" + task_instance_report(run_id)
        )
    print(f"  {'state':<34} {state}")
    return run_id


def task_instance_report(run_id: str) -> str:
    instances = api_get(
        f"/api/v2/dags/{NIGHTLY_DAG_ID}/dagRuns/{run_id}/taskInstances?limit=200"
    )
    lines = []
    for instance in sorted(instances["task_instances"], key=lambda row: row["task_id"]):
        lines.append(f"    {instance['state']:<10} {instance['task_id']}")
    return "\n".join(lines)


def check_cosmos_rendered_every_model(run_id: str) -> None:
    """Every dbt model the pipeline is specified to build was a task in this run.

    The one class of assertion in this file that reads Airflow's state rather than
    the warehouse, and there are two of them, for two reasons that are worth
    stating together.

    What a correct mart cannot tell you. A model that Cosmos silently skipped
    still leaves the table correct if an earlier run had built it. "Cosmos
    rendered the dbt project into tasks" is a claim about the graph, and a run's
    task instances are the only place a graph is observable from outside.

    What correct KPIs cannot tell you. A run that ignored its configuration and
    extracted some other window would be compared against the wrong expectation
    and the comparison would be meaningless, so the run's own report of the window
    it read is checked against the window that was requested.

    Both read what Airflow reports for a run this assertion triggered. Neither
    reads Cosmos's source, a DAG file, or a string in a file; a model that is
    missing from the graph fails here, and a model that is present but wrong
    fails at the comparison below.
    """
    instances = api_get(
        f"/api/v2/dags/{NIGHTLY_DAG_ID}/dagRuns/{run_id}/taskInstances?limit=200"
    )
    by_id = {row["task_id"]: row for row in instances["task_instances"]}
    unfinished = sorted(
        task_id
        for task_id, row in by_id.items()
        if row["state"] != "success"
    )
    if unfinished:
        raise GateFailure(
            "Not every task in the run succeeded: " + ", ".join(unfinished)
        )

    for model in DBT_MODELS:
        rendered = sorted(
            task_id for task_id in by_id if task_id.endswith(f".{model}.run")
        )
        if not rendered:
            raise GateFailure(
                f"No task in run {run_id} ran the dbt model {model!r}. Cosmos "
                f"rendered: {', '.join(sorted(by_id)) or '(nothing)'}"
            )
    show("dbt models rendered by Cosmos", ", ".join(DBT_MODELS))
    show("tasks in the run", f"{len(by_id)} (all success)")


def check_extraction_report(run_id: str, orders_in_window: int) -> None:
    """The run read the window it was asked to read, and as many rows as exist.

    The extraction task returns its window and its row counts as XCom, which is
    the run's own published output. Comparing it to the count in the source's
    pagination envelope is a check with teeth even though the run is reporting on
    itself: the envelope was read by the HTTP client above, at a different page
    size, and a pipeline that dropped a page or walked the wrong bounds disagrees
    with it here rather than quietly producing a smaller warehouse.

    It also closes the loop on the run configuration. The two runs this assertion
    makes differ in their logical dates, and this is where that is shown not to
    matter: the data came from the window in the configuration, not from the label.
    """
    report = api_get(
        f"/api/v2/dags/{NIGHTLY_DAG_ID}/dagRuns/{run_id}"
        "/taskInstances/extract_and_load_orders/xcomEntries/return_value"
    )["value"]

    read = (report["created_after"], report["created_before"])
    if read != (WINDOW_AFTER, WINDOW_BEFORE):
        raise GateFailure(
            f"Run {run_id} reports it read [{read[0]}, {read[1]}), but it was "
            f"asked for [{WINDOW_AFTER}, {WINDOW_BEFORE}). The run configuration "
            "did not reach the extraction, so the KPI comparison below would be "
            "between two different windows."
        )
    if report["rows_upserted"] != orders_in_window:
        raise GateFailure(
            f"Run {run_id} reports it upserted {report['rows_upserted']} orders, "
            f"but the source's envelope reports {orders_in_window} in this window."
        )
    show("window the run reports reading", f"[{read[0]}, {read[1]})")
    show("orders the run reports writing", report["rows_upserted"])


# --------------------------------------------------------------------------
# Comparison
# --------------------------------------------------------------------------


def digest(rows: dict[date, dict[str, Any]]) -> str:
    """A stable fingerprint of a whole KPI table.

    Printed on every run so that "the assertion is deterministic" is something a
    reader can see rather than something they are told: two runs a minute apart
    print the same digest, and so does a rerun tomorrow.
    """
    canonical = "\n".join(
        "|".join(
            str(value) for value in (day.isoformat(), *(rows[day][c] for c in KPI_COLUMNS))
        )
        for day in sorted(rows)
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compare(
    expected: dict[date, dict[str, Any]], actual: dict[date, dict[str, Any]]
) -> list[str]:
    problems: list[str] = []

    for day in sorted(set(expected) - set(actual)):
        problems.append(f"{day} missing from {FACT_RELATION}")
    for day in sorted(set(actual) - set(expected)):
        problems.append(
            f"{day} is in {FACT_RELATION} but not in the window; the window was not "
            "respected end to end"
        )

    for day in sorted(set(expected) & set(actual)):
        for column in KPI_COLUMNS:
            want, got = expected[day][column], actual[day][column]
            if want != got:
                problems.append(
                    f"{day} {column}: expected {want!r}, warehouse has {got!r}"
                )
    return problems


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def main() -> int:
    print(__doc__.strip().splitlines()[0])
    print(f"repository root: {REPO_ROOT}")
    print(f"window:          [{WINDOW_AFTER}, {WINDOW_BEFORE})")
    print(f"asserting:       {FACT_RELATION}")

    try:
        gate_environment_up()
        gate_cosmos_importable()
        gate_dbt_executable()
        gate_data_source_reachable()
        gate_one_pipeline_parses()
    except GateFailure as failure:
        print()
        print(f"GATE FAILED: {failure}")
        return 1

    rule("Gate 6/6  The pipeline assertion")

    try:
        expected, meta, pages = expected_daily_kpis()
    except GateFailure as failure:
        print(f"EXPECTATION FAILED: {failure}")
        return 1

    orders_in_window = meta["total_items"]
    print(
        f"  {'expected from the source':<34}"
        f"{len(expected)} days, {orders_in_window} orders, "
        f"{pages} pages of {EXPECTATION_PAGE_SIZE}"
    )
    show("expected kpi_digest", digest(expected))
    print()

    prepare_warehouse()

    try:
        first_run = trigger_and_wait("run1")
        check_cosmos_rendered_every_model(first_run)
        check_extraction_report(first_run, orders_in_window)

        raw_after_first = read_raw_counts()
        show("raw.orders", json.dumps(raw_after_first))

        first_facts = read_fact_table()
        show("first run kpi_digest", digest(first_facts))

        problems = compare(expected, first_facts)
        if problems:
            print()
            print("KPI MISMATCH after run 1:")
            for problem in problems[:25]:
                print(f"  {problem}")
            if len(problems) > 25:
                print(f"  ... and {len(problems) - 25} more")
            return 1
        print(f"  {'run 1':<34} {len(first_facts)} days match the independent expectation")

        # Idempotency. Same window, same conf, second run - only the run's label
        # differs. Everything the first run produced must be byte-identical
        # afterwards: the same rows, the same totals, the same count of rows in
        # the extract table. An extraction that appended, or a model that
        # accumulated, doubles here.
        second_run = trigger_and_wait("run2")
        check_extraction_report(second_run, orders_in_window)
        raw_after_second = read_raw_counts()
        show("raw.orders", json.dumps(raw_after_second))
        if raw_after_second != raw_after_first:
            raise GateFailure(
                "Re-running the same window changed the extract table:\n"
                f"  after run 1: {json.dumps(raw_after_first)}\n"
                f"  after run 2: {json.dumps(raw_after_second)}"
            )
        print(f"  {'run 2':<34} raw.orders unchanged")

        second_facts = read_fact_table()
        show("second run kpi_digest", digest(second_facts))
        if second_facts != first_facts:
            changed = sorted(
                str(day)
                for day in set(first_facts) | set(second_facts)
                if first_facts.get(day) != second_facts.get(day)
            )
            raise GateFailure(
                "Re-running the same window changed the KPI table on "
                f"{len(changed)} day(s), first at {changed[0]}. The pipeline is not "
                "idempotent."
            )
        print(f"  {'run 2':<34} {len(second_facts)} days identical to run 1")
    except GateFailure as failure:
        print()
        print(f"ASSERTION FAILED: {failure}")
        return 1

    print()
    print("=" * 78)
    print("PASS  the nightly pipeline produced correct daily KPIs over")
    print(f"      [{WINDOW_AFTER}, {WINDOW_BEFORE}), in one pass, twice, unchanged.")
    print(f"      {len(first_facts)} business days · {raw_after_first['rows']} orders · "
          f"kpi_digest {digest(first_facts)[:16]}…")
    print("      Every module from here extends this assertion; it does not add one.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
