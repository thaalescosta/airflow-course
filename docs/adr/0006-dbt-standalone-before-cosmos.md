# dbt is taught standalone before Cosmos

dbt is first run by hand from the CLI inside the container — models, `ref()`, tests, incremental strategies — with no Airflow involved. Cosmos is introduced afterwards, as orchestration of something already understood.

Cosmos's own quickstart assumes fluency with `dbt_project.yml`, `ref()`, incremental models, and schema tests, and teaching it to someone without that produces DAGs that reference models the learner cannot reason about. Running `dbt run` first also makes Cosmos's actual job legible: it does not run dbt, it schedules dbt. The dbt skills are portable to any orchestrator if Cosmos is later abandoned, which is a real risk worth insuring against.
