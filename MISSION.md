# Mission: Data Engineering with Apache Airflow & dbt

## Why

Pivot from data analyst to data engineer. I need working knowledge — not familiarity — of the tools a data engineer actually operates daily, so I can hold a real data engineering role and build pipelines that hold up in production. The portfolio projects that demonstrate this come second: competence first, artifacts follow.

## Success looks like

I can, unassisted:

- Read an unfamiliar DAG and explain what it does, when it will next run, and what a given task's failure would cause
- Write a DAG from scratch that fans out dynamically over a list fetched from the warehouse
- Say when to use data-triggered scheduling versus asset-triggered scheduling, and defend the choice
- Configure retries, timeouts, pools, and deadline alerts so a flaky upstream does not cause a cascade
- Debug a failure: read the task log, find the *root cause* rather than the symptom, fix it, and backfill the affected date range correctly
- Test a DAG before it ships
- Add a dbt model, wire it into the pipeline, write a test for it, and explain why the model belongs where it does
- Say when Airflow is the **wrong** tool

## Constraints

- Windows host; Airflow is not natively supported there. Runs via Astro CLI on Docker/WSL2.
- Self-directed. No teacher to check my work, so feedback loops must be built into the lessons.
- Self-first: I move at full speed and assume Python fluency. Every lesson still contains at least one explanation of something a Python developer would not already know, so the course stays publishable later.
- Study in substantial blocks, not daily sittings. A lesson plus its exercise should fit one sitting.
- Interleaved: concept, then immediate use in the ongoing project, then the next concept.
- One continuous project. Every lesson adds a real piece of it.
- All dependencies pinned exactly. Upgrades are taught, not done silently.

## Out of scope

- Airflow 2, SubDAGs, SLA callbacks, the `SequentialExecutor` — removed or dead as of 2026
- CeleryExecutor, KubernetesExecutor, and Astro Cloud deployment — taught only as "here is the shape of it," never run
- Spark, Kafka, Flink, and the wider streaming/batch ecosystem — a later curriculum, not this one
- Cloud warehouse credentials (BigQuery, Snowflake, Redshift) — Postgres and DuckDB locally instead
- Certification preparation (Airlie is defunct; Astronomer's exams are for their own stack)
