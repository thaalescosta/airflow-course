"""Extract a requested orders window and upsert it into the course warehouse."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

import psycopg2
from airflow.sdk import Connection, dag, get_current_context, task

WAREHOUSE_CONN_ID = "warehouse_default"
DEFAULT_ORDERS_API_BASE_URL = "http://orders-api:8000"
_ORDERS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS orders (
    order_id       text PRIMARY KEY,
    customer_id    text NOT NULL,
    status         text NOT NULL,
    currency       text NOT NULL,
    total_cents    integer NOT NULL,
    items          jsonb NOT NULL,
    created_at     timestamptz NOT NULL,
    ingested_at    timestamptz NOT NULL,
    updated_at     timestamptz NOT NULL,
    version        integer NOT NULL
)
"""
_ORDERS_UPSERT = """
INSERT INTO orders (
    order_id, customer_id, status, currency, total_cents, items,
    created_at, ingested_at, updated_at, version
)
VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
ON CONFLICT (order_id) DO UPDATE SET
    customer_id = EXCLUDED.customer_id,
    status = EXCLUDED.status,
    currency = EXCLUDED.currency,
    total_cents = EXCLUDED.total_cents,
    items = EXCLUDED.items,
    created_at = EXCLUDED.created_at,
    ingested_at = EXCLUDED.ingested_at,
    updated_at = EXCLUDED.updated_at,
    version = EXCLUDED.version
"""


def _as_rfc3339(value: datetime | str) -> str:
    parsed = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(value.replace("Z", "+00:00"))
    )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Window timestamps must include a timezone offset")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _select_window(
    run_conf: dict[str, Any], interval_start: datetime, interval_end: datetime
) -> tuple[str, str]:
    has_start = "created_after" in run_conf
    has_end = "created_before" in run_conf
    if has_start != has_end:
        raise ValueError(
            "Run configuration must provide both created_after and created_before"
        )

    if has_start:
        start = _as_rfc3339(run_conf["created_after"])
        end = _as_rfc3339(run_conf["created_before"])
    else:
        start = _as_rfc3339(interval_start)
        end = _as_rfc3339(interval_end)

    if datetime.fromisoformat(start.replace("Z", "+00:00")) >= datetime.fromisoformat(
        end.replace("Z", "+00:00")
    ):
        raise ValueError("created_after must be earlier than created_before")
    return start, end


def _fetch_orders(
    base_url: str, created_after: str, created_before: str
) -> list[dict[str, Any]]:
    orders: list[dict[str, Any]] = []
    page = 1
    visited_pages: set[int] = set()

    while True:
        if page in visited_pages:
            raise ValueError(f"Orders API repeated page {page}")
        visited_pages.add(page)
        query = urlencode(
            {
                "created_after": created_after,
                "created_before": created_before,
                "page": page,
                "page_size": 1000,
            }
        )
        with urlopen(f"{base_url.rstrip('/')}/orders?{query}", timeout=30) as response:
            payload = json.load(response)

        data = payload["data"]
        metadata = payload["meta"]
        if metadata["page"] != page:
            raise ValueError(
                f"Orders API returned page {metadata['page']} when page {page} was requested"
            )
        if not isinstance(data, list):
            raise ValueError("Orders API data must be a list")
        orders.extend(data)

        if not metadata["has_next"]:
            if metadata["next_page"] is not None:
                raise ValueError("Orders API supplied next_page while has_next was false")
            break
        next_page = metadata["next_page"]
        if not isinstance(next_page, int) or next_page <= page:
            raise ValueError(
                "Orders API must supply a later integer next_page when has_next is true"
            )
        page = next_page

    return orders


def _upsert_orders(cursor: Any, orders: list[dict[str, Any]]) -> None:
    cursor.execute(_ORDERS_TABLE_DDL)
    for order in orders:
        cursor.execute(
            _ORDERS_UPSERT,
            (
                order["order_id"],
                order["customer_id"],
                order["status"],
                order["currency"],
                order["total_cents"],
                json.dumps(order["items"]),
                order["created_at"],
                order["ingested_at"],
                order["updated_at"],
                order["version"],
            ),
        )


@dag(
    dag_id="pipeline_orders_ingestion",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["pipeline", "orders"],
)
def pipeline_orders_ingestion():
    @task(task_id="extract_and_load_orders")
    def extract_and_load_orders() -> dict[str, Any]:
        context = get_current_context()
        dag_run = context["dag_run"]
        created_after, created_before = _select_window(
            dag_run.conf or {},
            context["data_interval_start"],
            context["data_interval_end"],
        )
        orders = _fetch_orders(
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
                _upsert_orders(cursor, orders)
        return {
            "created_after": created_after,
            "created_before": created_before,
            "rows_received": len(orders),
            "rows_upserted": len(orders),
        }

    return extract_and_load_orders()


pipeline_orders_ingestion()
