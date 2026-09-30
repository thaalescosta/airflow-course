# The repository root is the Astro CLI project

The course repo is scaffolded with `astro dev init` at its root, so `dags/`, `Dockerfile`, `requirements.txt`, `.astro/`, `include/`, and `plugins/` sit at the top level, with `lessons/`, `reference/`, `assets/`, `learning-records/`, and `motion/` beside them. The alternative — a `course/` subdirectory holding lesson HTML next to a separate Airflow project — was rejected because it forces a choice between lessons that reference live, runnable DAG files and lessons that reference copies of them, and copies rot silently. A lesson that says "open `dags/pipeline/ingest.py`" must point at the file Airflow actually runs.

Within `dags/`, work is namespaced so the portfolio project stays legible: `dags/pipeline/` is the continuous project, `dags/exercises/` holds per-lesson throwaway DAGs, and `dags/dbt/` holds the dbt project Cosmos expects.
