# Resources

High-trust sources this course is grounded in. Everything cited in a lesson traces back to an entry here. Knowledge is gathered from these; parametric memory is never trusted.

## Knowledge

**Airflow documentation (stable = 3.3.2)** — https://airflow.apache.org/docs/apache-airflow/stable/index.html
The canonical reference for everything. Pinned version matters: read the version selector before following any instruction.

**Airflow 3 core concepts** — https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/overview.html
The component model: API server, DAG processor, scheduler, workers, triggerer. The "the executor is a config property, not a component" framing is the single most important idea in the course.

**Airflow public interface / Task SDK** — https://airflow.apache.org/docs/apache-airflow/stable/public-airflow-interface.html
What task code is allowed to import. In Airflow 3, task code uses `airflow.sdk` and reaches Airflow over the Execution API — it never touches the metadata DB directly.

**Airflow best practices doc** — https://airflow.apache.org/docs/apache-airflow/stable/best-practices.html
The official "how to write good DAGs" guidance. Cited as primary, not as blog opinion.

**Supported versions** — https://airflow.apache.org/docs/apache-airflow/stable/installation/supported-versions.html
Proof that Airflow 2 is EOL (2026-04-22) and 3.3.x is the maintained line.

**Airflow 3 release notes** — https://airflow.apache.org/docs/apache-airflow/3.0.0/release_notes.html
Read before every version bump. Each minor's breaking changes are listed here.

**Airflow 3.3.0 announcement** — https://airflow.apache.org/blog/airflow-3.3.0/
What the state/asset store adds and why it matters.

**Docker compose file (docs-hosted)** — https://airflow.apache.org/docs/apache-airflow/stable/docker-compose.yaml
Maintained by the project; note it is *no longer in the repo root*.

**Astro CLI** — https://github.com/astronomer/astro-cli
The local dev tool. `astro dev init` / `astro dev start` / `astro dev stop` / `astro dev parse` / `astro dev run`.

**Astro Runtime architecture** — https://www.astronomer.io/docs/astro/runtime-image-architecture
Why local dev is always LocalExecutor, and what Runtime adds.

**Astronomer Cosmos** — https://astronomer.github.io/astronomer-cosmos/
The dbt-to-Airflow bridge. The canonical first DAG is `dev/dags/basic_cosmos_dag.py` in the repo — tested in CI on Airflow 3, so it is guaranteed-current.

**Cosmos compatibility policy** — https://astronomer.github.io/astronomer-cosmos/policy/compatibility-policy.html
The version matrix. Establishes the `>=1.15.1,<1.16` pin.

**Cosmos execution modes** — https://astronomer.github.io/astronomer-cosmos/guides/run_dbt/execution-modes.html
Local, docker, kubernetes, watcher, virtualenv. Course uses `local`.

**Cosmos with the Astro CLI** — https://astronomer.github.io/astronomer-cosmos/getting_started/astro-cli-quickstart.html
The exact bridge between the two tools. Models the first Cosmos lesson.

**cosmos-demo** — https://github.com/astronomer/cosmos-demo
Official worked example. `git clone` + `astro dev start`. The `stg_customers.run` log line showing Cosmos shelling out to `dbt run --select` is a teaching artifact in its own right.

**dbt documentation** — https://docs.getdbt.com/
Models, materializations, incremental strategies, tests.

**dbt best practices** — https://docs.getdbt.com/best-practices
Staging/intermediate/marts layering and why the stg→int→fct naming convention is not just taste.

**State of Airflow 2026 (Astronomer)** — https://www.astronomer.io/press-releases/astronomer-releases-state-of-airflow-2026-report/
26% running Airflow 3, 84% preparing to upgrade. Useful for motivation and for knowing what a job market looks like.

## Foils

Existing resources studied deliberately, to be positioned against.

**Ansh Lamba — "Airflow Tutorial For Beginners (2026) | Apache Airflow Full Course"** — https://www.youtube.com/watch?v=IiczxlbQb8s
6h10m, published 2026-02-01, pinned to `apache/airflow:3.1.6` (released 2026-01-13). Repo: https://github.com/anshlambagit/Apache_Airflow_Full_Course

Correct where it matters: the architecture, DAG-file-processor and API-server topology, `airflow.sdk` imports, and asset vocabulary are all valid Airflow 3 and will not rot. The gaps are the point: **no dynamic task mapping** (`.expand()` appears in zero files, and it is the single most-used production feature), **no `TaskGroup`**, **no testing of any kind**, **no sensors, hooks, connections, or deferrable operators**, **no retries, pools, backfills, or idempotency**, **no capstone**, and **all 15 DAGs are `print()`/`echo` with no data**. The `airflow-triggerer` is deployed in his own compose file and never explained, though it is mandatory in Airflow 3.

Specific errors worth citing in lessons as anti-patterns:
- Teaches the legacy `ti.xcom_push(key='return_value')` idiom inside an Airflow 3 course, contradicting his own stated advice ("forget the old-school PythonOperators and messy XComs")
- Ch-13 "Assets" demonstrates asset scheduling by writing a string to `/opt/airflow/logs/data/` — asset-aware scheduling is the marquee Airflow 3 feature, shown against the logs directory
- `11_incremental_load.py` hardcodes `end_date=2026-01-31`, so that DAG will never schedule again
- Unedited `uv init` template `pyproject.toml`, `apache-airflow>=3.1.6` with no constraints file — only works because the Docker image hides the fragility
- README tells you to `pip install -r requirements.txt`; no such file exists
- A dedicated 5-minute sponsor segment slotted inside the conceptual preamble

## Wisdom (Communities)

- **Astronomer Academy** — https://academy.astronomer.io/ — free self-paced *Airflow 101 (Airflow 3)* and *DAG Authoring (Airflow 3)* prep modules. Free, current, and the best sanity check that this course is not missing something obvious.
- **Astronomer Academy certification exams** — https://www.astronomer.io/certification/ — $150, 75 MCQ, 60 min. Used as a *self-test* later, not as the curriculum.
- **Astronomer Airflow 3 Certification Crash Course (recording)** — https://www.astronomer.io/certification/ — free session recording with Marc Lamberti, Kenten Danas, Volker Janz.
- **r/dataengineering** — the place to take a design to in the wild. Post a real question from this course; read what practitioners reply to questions the docs answer badly.
- **Apache Airflow Slack** (ASF community) — for edge cases the issue tracker has not yet collected.

Note: Airlie certification is defunct (domain no longer resolves) — it was an Astronomer program, never ASF-official. "Astronomer Certified" *software* is retired; the *exam* survives as the Academy certification above.

## Gaps

- No published minimum RAM/CPU for `astro dev` from Astronomer. Inference only: ≥8 GB for the 4-container footprint. Verify empirically and record the real number.
- Whether Airflow **3.3.2** specifically works with Cosmos: 3.3.2 shipped 2026-09-17, six weeks after Cosmos 1.15.1 (2026-08-04), and the verified Cosmos↔Runtime table is dated 2026-07-23. Expected to work; unverified. Astro Runtime 3.3-7 ships 3.3.1, which sidesteps the question by accident.
- No substantive public review corpus exists for the foil video — 182K views, 369 comments, 0 GitHub issues, no forks. Its weaknesses are established here by reading its artifacts, not by reading criticism of it.
