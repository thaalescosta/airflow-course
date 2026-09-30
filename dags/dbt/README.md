# Standalone dbt project

This project runs dbt directly in its own container. Airflow and Cosmos do not
invoke or schedule it; the running Astro stack supplies only the separate
Postgres warehouse. The source declaration maps `raw.orders` to `public.orders`,
while `stg_orders` refers to that declaration with `source()` and builds as a
table in `analytics_staging`.

## Run locally

Use Git Bash from the repository root with Docker Desktop running, the Astro
stack started, and the local warehouse password present at
`.secrets/warehouse_pg_password`.

Build the standalone CLI image:

```sh
docker build --tag nightly-dbt-cli:1.0.0 --file dags/dbt/Dockerfile dags/dbt
```

Find the running warehouse and its Astro network. This avoids baking the
machine-specific Astro network name into project configuration:

```sh
WAREHOUSE_CONTAINER=$(docker ps --filter 'label=com.docker.compose.service=warehouse-postgres' --format '{{.ID}}' | head -n 1)
test -n "$WAREHOUSE_CONTAINER"
AIRFLOW_NETWORK=$(docker inspect --format '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' "$WAREHOUSE_CONTAINER" | grep '_airflow$')
REPO_ROOT=$(pwd -W)
```

Define a helper that runs the dbt CLI container on that network. The project
directory is mounted read-write so generated artifacts remain on the host; the
warehouse password is mounted read-only and is not included in the image or
project files.

```sh
dbt() {
  MSYS_NO_PATHCONV=1 docker run --rm \
    --network "$AIRFLOW_NETWORK" \
    --mount "type=bind,source=$REPO_ROOT/dags/dbt,target=/workspace" \
    --mount "type=bind,source=$REPO_ROOT/.secrets/warehouse_pg_password,target=/run/secrets/warehouse_pg_password,readonly" \
    nightly-dbt-cli:1.0.0 dbt "$@"
}

dbt debug --project-dir /workspace --profiles-dir /workspace/profiles
dbt run --project-dir /workspace --profiles-dir /workspace/profiles
dbt test --project-dir /workspace --profiles-dir /workspace/profiles
dbt show --project-dir /workspace --profiles-dir /workspace/profiles --select stg_orders --limit 5
```

Inspect the materialized table directly in the warehouse:

```sh
docker exec "$WAREHOUSE_CONTAINER" psql -U warehouse -d warehouse \
  -c 'select order_id, customer_id, status, total_cents from analytics_staging.stg_orders limit 5'
```

After `dbt run`, `target/manifest.json` describes the parsed project and
`target/run_results.json` records the run results. Both are kept under this
project's ignored `target/` directory, so they are readable locally but not
committed.