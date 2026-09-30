# Environment baseline (verified)

Everything in this file was measured on the course machine, not read from a
document. It is the reference a lesson cites when it needs to say "this is what
the environment actually does". Re-verify rather than trust: the commands are
given so the numbers can be regenerated.

Measured on 2026-09-30. Host: Windows 11, git-bash, not elevated.

## 1. Cold start

Two phases. The first is once per machine; the second is once per clone. Run both
in a **Windows shell** — Windows PowerShell or git-bash. Not a WSL terminal, not
an elevated shell.

```sh
# Phase 1 — once per machine. --skip-dependencies is load-bearing: from CLI
# 1.32.0 the default install drags in Podman as the container engine. We want
# the Docker runtime that is already on the box.
winget install -e --id Astronomer.Astro -v 1.46.0 --skip-dependencies

# Phase 2 — once per clone, at the repository root (ADR 0001).
astro dev init --runtime-version 3.3-7 --force
astro dev start --no-browser --wait 5m
```

`--runtime-version 3.3-7` is the exact pin ADR 0004 requires. `--force` is
needed because the repository root already holds committed files. Without it
`astro dev init` stops and asks:

```
C:\Projects\airflow-course is not an empty directory. Are you sure you want to
initialize a project here? (y/n)
```

Answering `y` is equivalent to `--force`. Nothing has to be moved out of the
way to make room for the Astro project.

`astro dev start` in Docker mode is not a foreground command — it returns once
the webserver reports healthy, bounded by `--wait`. It will not hang a session.

The resulting stack is **eight** containers, not the five the generated
`README.md` claims: `postgres`, `warehouse-postgres` and `orders-api` (both added
by `docker-compose.override.yml` — see §7), `db-migration` (one-shot, runs then
exits), `scheduler`, `dag-processor`, `api-server`, `triggerer`. Seven of them stay
up; `db-migration` exits. Note that `orders-api` is built from a sibling checkout
rather than pulled, so a fresh machine has one extra step before the stack comes
up; §7 says where it lives.

```
➤ Airflow UI: http://localhost:8080
➤ Postgres Database: postgresql://localhost:5432/postgres
```

`astro dev parse` is the cheapest proof the project is sound, and it exits
non-zero on a DAG import error. That is test seam 1.

## 2. The container engine is Docker, not Podman

This is a check, not an observation. Run all three; each is a positive signal
that cannot be produced by a Podman-backed run.

```sh
# (a) which Docker context the CLI would talk to
docker context ls
#   desktop-linux *   Docker Desktop   npipe:////./pipe/dockerDesktopLinuxEngine

# (b) the engine and the resources the containers actually get
docker info --format 'Name={{.Name}} Driver={{.Driver}} NCPU={{.NCPU}} MemTotal={{.MemTotal}}'
#   Name=docker-desktop Driver=overlayfs NCPU=16 MemTotal=8008667136

# (c) Astro stamps its own Docker-mode marker on every container it starts
docker ps --filter "label=com.docker.compose.project=airflow-course_d896a3" \
  --format '{{.Names}}' |
  while read n; do
    printf '%s io.astronomer.docker.cli=%s\n' "$n" \
      "$(docker inspect "$n" --format '{{index .Config.Labels "io.astronomer.docker.cli"}}')"
  done
#   airflow-course_d896a3-api-server-1 io.astronomer.docker.cli=true
#   airflow-course_d896a3-triggerer-1 io.astronomer.docker.cli=true
#   airflow-course_d896a3-dag-processor-1 io.astronomer.docker.cli=true
#   airflow-course_d896a3-scheduler-1 io.astronomer.docker.cli=true
#   airflow-course_d896a3-postgres-1 io.astronomer.docker.cli=true
```

(c) is the load-bearing one: `io.astronomer.docker.cli=true` is set by the Astro
CLI's Docker code path, so it cannot appear on a Podman run.

There is a fourth signal, available only during `astro dev start --verbosity
debug`, and it is the most direct — BuildKit names the builder instance it used:

```
#0 building with "desktop-linux" instance using docker driver
#4  [1/8] FROM astrocrpublic.azurecr.io/runtime:3.3-7@sha256:927684ace161d570e1e1fcd9a7c3d2cc99dfaefbc1ada2e566eca2b4dbca5708
```

**Caveat, and it matters here.** `podman` *is* present on this machine —
`C:\Users\ThalesCosta\AppData\Local\Programs\Podman\podman.exe`, Podman CLI
6.1.3 — installed before the course work began, not by the `--skip-dependencies`
install, which reported `Dependencies skipped.` So "Podman is not installed" is
**not** a valid check on this box. Only the positive signals above are.

## 3. What the container reports about itself

Read off the running container, never off a docs page:

```sh
docker exec airflow-course_d896a3-api-server-1 airflow version
#   3.3.1+astro.4
```

Corroborated from the image labels, which is a second independent read:

```
io.astronomer.docker.runtime.version = 3.3-7
io.astronomer.docker.airflow.version = 3.3.1+astro.4
io.astronomer.docker.airflow-task-sdk.version = 1.3.1+astro.2
io.astronomer.docker.python.version = 3.14
```

## 4. Hardware floor — this is inference, not a published minimum

> **Inference.** Astronomer publishes no minimum RAM or CPU figure for
> `astro dev`. Everything below is measured on this machine and generalised by
> judgement. Do not quote it as a vendor minimum.

| Quantity | Value | How measured |
| --- | --- | --- |
| Host physical RAM | 16,540,614,656 B (15.41 GiB) | `Win32_ComputerSystem.TotalPhysicalMemory` |
| RAM the containers may use | 8,008,667,136 B (7.46 GiB) | `docker info` `MemTotal` — the WSL2 VM, not the host |
| CPUs | 16 logical | `docker info` `NCPU` |
| Idle footprint, 5 running containers | ~1,029 MiB | `docker stats --no-stream` |
| Peak footprint during a real DAG run | ~1,470 MiB (1.44 GiB) | 100× 1 s samples of `docker stats` while `astro dev run dags test example_astronauts` ran |
| Peak per container under load | api-server 508 MiB, scheduler 414 MiB, triggerer 286 MiB, dag-processor 210 MiB, postgres 51 MiB | same samples |
| Local image size | 1.9 GB | `docker images` |

Two things this settles, both of which contradict the working assumption in
`RESOURCES.md` → Gaps:

1. The inference recorded there is "**≥8 GB for the 4-container footprint**".
   The footprint is five running containers plus a one-shot sixth, and it does
   not need 8 GB — the stack ran to completion in **7.46 GiB of ceiling with
   ~1.4 GiB actually used**, about a fifth of what was available. A working
   floor inferred from these numbers is nearer **2 GB allocated**, with CPU not
   a binding constraint at all (peak observed was under 2% of one core per
   container, on a 16-core box).
2. That run also had to fit *under* the 8 GB the earlier inference assumed —
   Docker Desktop capped the VM at 7.46 GiB, below the assumed bar, and
   nothing broke. The earlier figure was conservative by roughly an order of
   magnitude, not tight.

The honest floor therefore is stated as an inference and re-tested whenever the
container count grows, because a DAG that fans out over a large dynamic task
mapping is what will actually move these numbers.

## 5. The version gap, recorded as course content

| | Version | Source |
| --- | --- | --- |
| What the container runs | **3.3.1+astro.4** | `airflow version` inside the container, §3 |
| What the documentation describes | **3.3.2** | `RESOURCES.md` → *Airflow documentation (stable)*; confirmed against the docs' own version selector, which reads `Version: 3.3.2` |
| Astro Runtime supplying it | **3.3-7** | `Dockerfile` at the repository root; digest confirmed at build time in §2 |

The gap is real and it is **deliberate**. ADR 0003 names it as a consequence
accepted rather than hidden, and ADR 0004 pins the image to `3.3-7` on purpose
even though a newer Airflow patch exists. A learner who reads the stable docs
and then reads their own container sees two different version numbers on the
same day. That is the lesson, not a defect to smooth over: the CLI's release
cadence trails the ASF patch line, and the local runtime is chosen for a tested
composition (its bundled Task SDK, its provider set) rather than for the newest
patch number.

A second-order consequence worth teaching: because the local runtime is
`3.3.1+astro.4` and not `3.3.2`, the open question in `RESOURCES.md` → Gaps
about Cosmos `>=1.15.1,<1.16` on Airflow 3.3.2 **does not arise locally**. It
stays open, and it is only answered by an explicit Runtime upgrade — which
ADR 0004 makes its own lesson.

## 6. Why the compose configuration is a capture, not a file

ADR 0003 concedes that `astro dev start` "hides the deployment shape". It hides
it more completely than expected: the CLI builds its compose model in memory and
**never writes a compose file to disk**. Two independent observations:

```sh
# (a) the containers record no config file at all
docker inspect airflow-course_d896a3-postgres-1 \
  --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}'
#   (empty)

# (b) watching TEMP and the project root for a new *.yml / *.yaml across a full
#     `astro dev start` finds nothing — even at --verbosity debug
```

So the effective compose configuration is recovered from the running containers
instead and committed here:

- `reference/generated-compose.json` — the resolved shape: six services, image,
  command, entrypoint, environment, ports, mounts, depends-on, restart policy,
  and the Astro image labels.
- `reference/capture-compose.py` — the script that produced it, kept so the
  capture is repeatable rather than hand-copied.

Regenerate with the stack up:

```sh
python reference/capture-compose.py > reference/generated-compose.json
```

The `Dockerfile` needs no such treatment — `astro dev init` writes it, it is
committed, and it is one line: `FROM astrocrpublic.azurecr.io/runtime:3.3-7`.

## 7. The course warehouse is a second Postgres, not Astro's

`docker-compose.override.yml` adds one service, `warehouse-postgres`, to the
stack. `astro dev start` merges that file into the in-memory compose model it
builds (§6). Astro's own `postgres` remains the **metadata** database: it
holds `dag`, `task_instance`, `dag_run`, `connection` and the rest, it is
owned by the `db-migration` one-shot, and in Airflow 3 task code may not
write to it. The warehouse is a different engine, kept apart on every axis:

| | metadata database | course warehouse |
| --- | --- | --- |
| service | `postgres` | `warehouse-postgres` |
| database | `postgres` | `warehouse` |
| role | `postgres` | `warehouse` |
| host port | 5432 | 5433 |
| volume | `postgres_data` | `warehouse_data` |
| image | `docker.io/postgres:15` (floating) | `docker.io/postgres:15.14-alpine3.22` (pinned) |
| reached by | Airflow internals | the `warehouse_default` connection, from task code |

Reusing Astro's Postgres would be a course-simplification that teaches the
wrong thing: pipeline tables would sit beside `dag_run` and `connection` in
one database, so an `astro dev kill --volumes` or a stray
`DROP SCHEMA public CASCADE` would destroy the warehouse, and the lesson
"Airflow 3 forbids task code to write the metadata DB" would be demonstrated
by the code violating it. In production the warehouse is a managed engine
(BigQuery/Snowflake/Redshift) and the credential comes from a secrets backend
rather than a local container's env var.

### Two things about the override file that are not guessable

Both were found the hard way; re-verify rather than trust.

**1. A service added by the override needs `networks: [airflow]`.** The base
model declares its network under the *key* `airflow`, which is why the network
is created as `<project>_<hash>_airflow`. An override service that omits
`networks` is placed on a second, auto-created network
(`<project>_<hash>_default`) that the Airflow containers are not attached to,
and the failure is a DNS error, not a connectivity error:

```sh
docker exec airflow-course_d896a3-scheduler-1 \
  python -c "import socket; print(socket.gethostbyname('warehouse-postgres'))"
# gaierror: [Errno -2] Name or service not known
```

Referencing the key `airflow` keeps the project-path hash out of the file, so
it survives a re-clone to a different directory. Do **not** set
`container_name` on this service: it replaces the service name as the network
alias, which is the very name the Airflow containers resolve.

**2. `${VAR}` is not interpolated from the project's `.env`.** Astro builds the
compose model in-process with compose-go, not by shelling out to the compose
CLI, and it does not load `.env` into the environment it interpolates from. A
`${WAREHOUSE_PG_PASSWORD:?...}` in the override therefore fails in a fresh
shell, even though `.env` is right there and correct:

```
Error: error creating docker-compose project: failed to load project: error
while interpolating services.warehouse-postgres.environment.POSTGRES_PASSWORD:
required variable WAREHOUSE_PG_PASSWORD is missing a value
```

It *does* pass if the variable happens to be exported in the invoking shell,
which is exactly what makes it a trap: the fix appears to work on the machine
where it was found. The password is therefore mounted as a Docker secret
instead — `POSTGRES_PASSWORD_FILE: /run/secrets/warehouse_pg_password`, read
from `./.secrets/warehouse_pg_password` (gitignored, and in `.dockerignore` so
it cannot reach the image build context).

### The connection, and where the secret is allowed to be visible

Seeded out of band with the Airflow 3 CLI, never in a DAG file:

```sh
docker exec airflow-course_d896a3-api-server-1 airflow connections add \
  warehouse_default --conn-type postgres --conn-host warehouse-postgres \
  --conn-port 5432 --conn-schema warehouse --conn-login warehouse \
  --conn-password "$PW"
# Successfully added `conn_id`=warehouse_default : generic://warehouse:******@warehouse-postgres:5432/warehouse
```

Read in task code with `airflow.sdk.Connection.get(conn_id)`. Three measured
things about the secret's visibility, all inside a container:

- `airflow connections list` masks it (`generic` type, no password shown).
- `airflow connections get` **prints it in cleartext**, table and `-o json`.
  With DB access the CLI can read what Fernet encrypted; the encryption stops
  the value at rest, not an admin with the metadata DB.
- `Connection.get()` called *outside* a task raises
  `AirflowNotFoundException: The conn_id 'warehouse_default' isn't defined`.
  The Task SDK resolves connections through the task's execution context over
  the Execution API, so outside a task there is nothing to resolve them
  against. This is the Airflow 3 boundary, observed rather than quoted.

### One stale row to expect in `airflow dags list`

`airflow dags list` shows `example_astronauts`
(`/usr/local/airflow/dags/exampledag.py`) although no such file exists in the
repo or in the container — `dags/` is a bind mount of the repository's `dags/`,
and `exampledag.py` is in neither. It is a leftover `dag` table row from an
earlier run, re-parsed before the file was removed:

```sh
docker exec airflow-course_d896a3-postgres-1 psql -U postgres -d postgres \
  -t -A -F' | ' -c "select dag_id, fileloc, last_parsed_time from dag order by dag_id;"
# example_astronauts | /usr/local/airflow/dags/exampledag.py | 2026-09-30 05:09:08+00
```

The API the UI actually renders is not affected — it reads the live bundle and
reports only real DAGs:

```sh
curl -s -H "Authorization: Bearer $TOK" 'http://localhost:8080/api/v2/dags'
# total: 2  ->  pipeline_nightly_order_kpis, pipeline_warehouse_connection_check
```

So `airflow dags list` and the UI can disagree. The UI is the one to trust.

The same staleness has a second shape, and it bit harder than `example_astronauts`
did. Deleting a DAG file does **not** remove its row: `dags/pipeline/orders_ingestion.py`
and `dags/pipeline/dbt_transform.py` were removed from the repository and a
`dag` row survived for each, `airflow dags list` kept reporting them, and the API
reported them too — not as stale extras, but as live DAGs, one of them carrying
`timetable_summary = 0 0 * * *`. Airflow had a scheduled nightly run queued for
a pipeline that no longer had a file.

Neither `airflow dags reserialize` nor a re-parse cycle clears it; the row is
only removed by

```sh
echo y | docker exec -i airflow-course_d896a3-scheduler-1 \
  airflow dags delete pipeline_orders_ingestion
# Removed 3 record(s)
```

After which `dag.last_parsed_time` is fresh, `is_stale` is false for both
surviving DAGs, and the API reports the reduced set. The lesson for the course:
`dags_are_paused_at_creation` is a local row too, so both the paused flag and the
row itself are state a clone does not inherit. Gate 5 in
`tests/assert_pipeline_kpis.py` asserts the parsed DAG set against `EXPECTED_DAGS`,
which is what catches this class of drift before it can act on anything.

One cosmetic leftover survives the cleanup: `serialized_dag` can hold more than
one row per `dag_id` after repeated re-serialization of the same file, and
`airflow dags list` — which reads that table — then prints the same `dag_id`
twice. The API dedupes by `dag_id` and the `dag` table is correct, so this is
display-only. Rows written at 15:26 and 15:58 outlived the row written at 16:28
in this environment.

## 8. In Airflow 3, `schedule="@daily"` is not a data interval

The single most expensive surprise in the course, found by a scheduled run rather
than by a test, and worth writing down because the string looks like it means what
it says.

`schedule="@daily"` resolves to **`CronTriggerTimetable`**, whose data interval is a
single instant. Measured inside the container:

```sh
docker exec airflow-course_d896a3-scheduler-1 python -c "
import datetime; from airflow.timetables.trigger import CronTriggerTimetable
from airflow.timetables.interval import CronDataIntervalTimetable
for tt in (CronTriggerTimetable('0 0 * * *', timezone='UTC'),
           CronDataIntervalTimetable('0 0 * * *', timezone='UTC')):
    print(type(tt).__name__, tt.infer_manual_data_interval(
        run_after=datetime.datetime(2026,10,1,tzinfo=datetime.timezone.utc)))"
# CronTriggerTimetable      DataInterval(start=2026-10-01 00:00:00+00:00, end=2026-10-01 00:00:00+00:00)
# CronDataIntervalTimetable DataInterval(start=2026-09-30 00:00:00+00:00, end=2026-10-01 00:00:00+00:00)
```

A pipeline that extracts "the window between `data_interval_start` and
`data_interval_end`" therefore gets `start == end` on every scheduled run and
raises before reading a row:

```
ValueError: created_after must be earlier than created_before
  File ".../dags/pipeline/nightly_order_kpis.py", line 81, in extract_and_load_orders
  File ".../dags/pipeline/orders_extract.py", line 124, in select_window
```

`CronDataIntervalTimetable` triggers at the same midnight and gives the interval
[2026-09-30, 2026-10-01), so the run labelled 2026-10-01 extracts 2026-09-30. That
is what `dags/pipeline/intervals.py` declares, and the nightly pipeline uses it.

It survived as long as it did because it cannot show up in the obvious checks. The
damage is only in the **metadatabase**, not in a parse:

```sh
docker exec airflow-course_d896a3-postgres-1 psql -U postgres -d postgres \
  -c "select run_id, run_type, data_interval_start, data_interval_end, state \
      from dag_run where dag_id='pipeline_nightly_order_kpis';"
#   run_id                                | run_type  |      logical_date      |   data_interval_start   |   data_interval_end   |  state
# ----------------------------------------+-----------+------------------------+-------------------------+------------------------+---------
#  manual_1790782322                     | manual    | 2026-02-01 00:00:00+00 | 2026-02-01 00:00:00+00 | 2026-02-01 00:00:00+00 | success
#  scheduled__2026-09-30T00:00:00+00:00   | scheduled | 2026-09-30 00:00:00+00 | 2026-09-30 00:00:00+00 | 2026-09-30 00:00:00+00 | failed
```

Both rows have `start == end` — including the successful one, because a **manual**
run passes only when its window comes from `conf`, so the interval is never read.
A DAG can be unpaused, import cleanly, render nine tasks, and pass every check you
trigger by hand while failing every single night.

Two consequences for how the course asserts things. `tests/assert_pipeline_kpis.py`
triggers with an explicit window and then reads back *the run's own reported
window* rather than assuming it, because the two are the same thing only by
agreement. And a scheduled run is a distinct behaviour from a manual one, which is
why the regression test in `tests/test_orders_ingestion.py` asserts the timetable's
interval directly instead of asserting it through a run.

## 9. The Astro CLI is one release behind the pin in §1

| | Version | Source |
| --- | --- | --- |
| §1's install command | **1.46.0** | `winget install -e --id Astronomer.Astro -v 1.46.0` |
| What is installed here | **1.45.0** | `astro version`; `winget list --id Astronomer.Astro` reports `1.45.0  1.46.0` |
| Release date of 1.46.0 | **2026-09-29**, one day before this measurement | the GitHub release for `v1.46.0` |

§1's command was therefore written against a release that landed after this stack
was built. The discrepancy is recorded rather than quietly closed, and the upgrade
is deferred on purpose: the `v1.46.0` changelog contains *"Bump local Postgres to
15 and pin existing projects to their version"*, which changes the compose model
this repository's `docker-compose.override.yml` is merged into (§6, §7). That is a
deliberate, re-verified step — rebuild the stack, re-run
`tests/assert_pipeline_kpis.py`, re-capture `reference/generated-compose.json` — and
not something to do as a side effect of writing a lesson.

ADR 0004's pin is on the *runtime image*, and that is unaffected: the container
still reports `3.3.1+astro.4`. §5's version gap is a different thing and still
stands — that one is about Airflow's patch line, not about the CLI.
