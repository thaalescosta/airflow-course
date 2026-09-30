"""The continuous project's nightly pipeline: extract, then transform.

One DAG, not two. The project's claim is that a nightly e-commerce order
analytics pipeline runs from a synthetic API into a warehouse through dbt into
daily KPI tables, and a pipeline split across two independently scheduled DAGs
would make the claim untrue: nothing would guarantee the transform ran after the
extract, and the ordering would live in an operator's head. One DAG puts the
ordering in the dependency graph, where Airflow holds it.

    orders-api ─▶ extract_and_load_orders ─▶ cosmos_dbt_project ─▶ fct_daily_order_kpis

Three things this file is careful about:

* The window comes from Airflow, not from a constant. A daily schedule runs on
  its data interval; a run configuration with both bounds overrides it. That is
  what makes the pipeline backfillable later without touching this file. Both
  halves of that only hold because the schedule is the data-interval timetable
  in `pipeline/intervals.py` rather than the string `"@daily"`.
* The Cosmos task group is a component in a DAG that was written by hand, not a
  whole DAG generated from a dbt project. The hand-written extraction task on
  one side of it is the point: the boundary between "what Cosmos automates" and
  "what I wrote" stays visible.
* Nothing here checks the warehouse. A pipeline does not assert that it
  produced correct numbers; `tests/assert_pipeline_kpis.py` does, from outside,
  against independently computed values. A pipeline that graded its own output
  would be grading its homework.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg2
from airflow.sdk import Connection, dag, get_current_context, task
from cosmos import DbtTaskGroup, ExecutionConfig, ProfileConfig, ProjectConfig
from cosmos.constants import ExecutionMode
from cosmos.profiles import PostgresUserPasswordProfileMapping

from pipeline.intervals import NIGHTLY_SCHEDULE
from pipeline.orders_extract import fetch_orders, select_window, upsert_orders

WAREHOUSE_CONN_ID = "warehouse_default"
DEFAULT_ORDERS_API_BASE_URL = "http://orders-api:8000"
DBT_PROJECT_PATH = Path(__file__).resolve().parents[1] / "dbt"

profile_config = ProfileConfig(
    profile_name="airflow_course",
    target_name="local",
    profile_mapping=PostgresUserPasswordProfileMapping(
        conn_id=WAREHOUSE_CONN_ID,
        profile_args={"schema": "analytics", "threads": 4},
        disable_event_tracking=True,
    ),
)


@dag(
    dag_id="pipeline_nightly_order_kpis",
    schedule=NIGHTLY_SCHEDULE,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["pipeline", "orders", "dbt", "cosmos"],
    description=(
        "Nightly order KPIs: extract a window from the orders API into the "
        "warehouse, then render the dbt project into tasks and run it."
    ),
)
def pipeline_nightly_order_kpis():
    @task(task_id="extract_and_load_orders")
    def extract_and_load_orders() -> dict[str, Any]:
        """Read this run's window from the API and upsert it into `raw.orders`.

        Idempotent by identity: rows are keyed by the source's own `order_id`
        and written with an upsert, so re-running the same window replaces what
        is already there instead of appending beside it. That is what lets a
        correction - the same order_id at a higher `version` with a different
        body - land as an update.
        """
        context = get_current_context()
        dag_run = context["dag_run"]
        created_after, created_before = select_window(
            dag_run.conf or {},
            context["data_interval_start"],
            context["data_interval_end"],
        )
        orders = fetch_orders(
            os.environ.get("ORDERS_API_BASE_URL", DEFAULT_ORDERS_API_BASE_URL),
            created_after,
            created_before,
        )
        connection = Connection.get(WAREHOUSE_CONN_ID)
        with psycopg2.connect(
            host=connection.host,
            port=connection.port,
            dbname=connection.schema,
            user=connection.login,
            password=connection.password,
        ) as database:
            with database.cursor() as cursor:
                upsert_orders(cursor, orders)
        return {
            "created_after": created_after,
            "created_before": created_before,
            "rows_received": len(orders),
            "rows_upserted": len(orders),
        }

    dbt_project = DbtTaskGroup(
        group_id="cosmos_dbt_project",
        project_config=ProjectConfig(DBT_PROJECT_PATH),
        profile_config=profile_config,
        execution_config=ExecutionConfig(
            execution_mode=ExecutionMode.LOCAL,
        ),
    )

    extract_and_load_orders() >> dbt_project


pipeline_nightly_order_kpis()
