"""Extract a requested orders window and upsert it into the course warehouse.

The first hand-written DAG of the continuous project, and the shape every later
hand-written task follows: the window comes from Airflow, the rows come from a
service addressed by name over the container network, and the credential comes
from the connection store rather than from this file.

The logic lives in ``dags/pipeline/orders_extract.py`` and nothing but Airflow
lives here. A DAG file is a wiring diagram; anything worth reasoning about on
its own belongs where it can be read without a scheduler in the picture, which
is also where the second test seam reaches it.

The schedule is ``pipeline.intervals.NIGHTLY_SCHEDULE`` rather than the string
``"@daily"`` this DAG used to carry, because in Airflow 3 that string resolves
to a timetable with a zero-length data interval and every scheduled run of this
DAG then failed on its window. Read ``intervals.py`` before changing it back.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import psycopg2
from airflow.sdk import Connection, dag, get_current_context, task

from pipeline.intervals import NIGHTLY_SCHEDULE
from pipeline.orders_extract import fetch_orders, select_window, upsert_orders

WAREHOUSE_CONN_ID = "warehouse_default"
DEFAULT_ORDERS_API_BASE_URL = "http://orders-api:8000"


@dag(
    dag_id="pipeline_orders_ingestion",
    schedule=NIGHTLY_SCHEDULE,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["pipeline", "orders"],
)
def pipeline_orders_ingestion():
    @task(task_id="extract_and_load_orders")
    def extract_and_load_orders() -> dict[str, Any]:
        """Read the run's window from the API and write it to the warehouse.

        The returned dictionary is XCom, which is stored in Airflow's metadata
        database and rendered in the task UI, so it reports counts and window
        bounds and nothing else. It is the run's own evidence that it read what
        it was asked to read.
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

    return extract_and_load_orders()


pipeline_orders_ingestion()
