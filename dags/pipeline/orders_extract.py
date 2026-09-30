"""The pipeline's extraction logic, with no Airflow in it.

Why this file exists. Extraction was originally written inline in the DAG file,
next to the tasks that called it. That is fine while the logic has one caller and
it does not survive a second one: when the nightly KPI pipeline arrived needing
the same extraction, the options were to duplicate a hundred lines of window
selection, pagination and upsert, or to reach across DAG files and import
private helpers out of one. Both are worse than putting the logic here. The two
DAGs that forced the extraction then collapsed into ``nightly_order_kpis.py``,
which is the single pipeline — so this file now has one caller again, and it is
still not inlined, because the reason it was pulled out was never only the caller
count.

The module boundary is also the boundary of the course's second test seam.
Everything here is a pure function of its arguments plus the network and the
warehouse, so it can be tested without a scheduler — which is what
``tests/test_orders_ingestion.py`` does. Airflow-specific concerns (the
connection id, ``get_current_context``, the DAG decorators) stay in the DAG
file and nowhere else.

Nothing here knows what a KPI is. Extraction moves rows; dbt decides what they
mean. That separation is why the pipeline assertion can compute its expectation
straight from the API without consulting a single model.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

# The API's contractual ceiling on `page_size` (reference/orders-api-contract.md).
# Asking for the largest page the source will serve is the right production
# choice: fewer round-trips per window, and the loop below still has to handle
# more than one page, because a window can hold more rows than any one page.
MAX_PAGE_SIZE = 1000

REQUEST_TIMEOUT_SECONDS = 30

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

# An upsert, not an insert, and that is the whole late-arrival story at this
# layer. `raw.orders` is keyed by the source's own order_id, so a window that is
# read a second time replaces the rows it already holds rather than appending
# beside them. That is what makes a correction - the same order_id with a higher
# `version` and a different body - land as an update instead of a duplicate.
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


def as_rfc3339(value: datetime | str) -> str:
    """Render an aware datetime as the UTC RFC 3339 string the API expects.

    The offset is not optional. The source rejects a naive timestamp rather
    than reading it in the server's local zone, so a window built from a naive
    datetime has to fail here rather than become a silent, machine-dependent
    query.
    """
    parsed = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(value.replace("Z", "+00:00"))
    )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Window timestamps must include a timezone offset")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def select_window(
    run_conf: dict[str, Any], interval_start: datetime, interval_end: datetime
) -> tuple[str, str]:
    """Resolve the half-open `[created_after, created_before)` window to extract.

    A DAG run's own data interval is the default, which is the nightly case: the
    run labelled Monday extracts Sunday. Supplying both bounds in the run
    configuration overrides it, which is the backfill case. Supplying one bound
    is rejected rather than guessed at, because a half-specified window would
    silently extract the whole universe on one side.
    """
    has_start = "created_after" in run_conf
    has_end = "created_before" in run_conf
    if has_start != has_end:
        raise ValueError(
            "Run configuration must provide both created_after and created_before"
        )

    if has_start:
        start = as_rfc3339(run_conf["created_after"])
        end = as_rfc3339(run_conf["created_before"])
    else:
        start = as_rfc3339(interval_start)
        end = as_rfc3339(interval_end)

    if datetime.fromisoformat(start.replace("Z", "+00:00")) >= datetime.fromisoformat(
        end.replace("Z", "+00:00")
    ):
        raise ValueError("created_after must be earlier than created_before")
    return start, end


def fetch_orders(
    base_url: str, created_after: str, created_before: str
) -> list[dict[str, Any]]:
    """Every order in the window, walked page by page.

    The window is held constant across pages and the loop follows the source's
    own `meta.next_page` rather than incrementing a counter. Those are different
    designs: a counter assumes the filtered result set is stable while the
    window is being read, which is exactly the assumption a source that can
    late-arrive rows breaks. The visited-page set is the belt to that braces -
    a source that ever points `next_page` backwards would otherwise spin here
    forever rather than fail.
    """
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
                "page_size": MAX_PAGE_SIZE,
            }
        )
        with urlopen(
            f"{base_url.rstrip('/')}/orders?{query}", timeout=REQUEST_TIMEOUT_SECONDS
        ) as response:
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


def upsert_orders(cursor: Any, orders: list[dict[str, Any]]) -> None:
    """Create `raw.orders` if it is missing, then write every order by identity."""
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
