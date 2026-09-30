"""The second test seam: the extraction's pure functions, with no scheduler.

Which seam this file is, and which it is not. The course's *primary* seam is
``tests/assert_pipeline_kpis.py``, and its rule is that it asserts externally
observable behaviour only - what is in the warehouse, never what a function looks
like or what a string in a file says. That rule exists because the primary seam's
job is to judge the whole pipeline, and a pipeline judged on its own internals
can be renamed into passing.

This file is the other thing: unit tests at the boundary of a task, calling the
functions a task is built from and asserting what they return. There is no
pipeline here to judge, so there is nothing to rename. These tests are allowed to
be about shapes - ``ON CONFLICT (order_id) DO UPDATE`` is a real part of the
contract with the database, and a duplicate-row bug would not show up in any
end-to-end assertion that happened to use a window with no repeated order.

The boundary that keeps this honest is ``dags/pipeline/orders_extract.py`` being
Airflow-free. A module that imports ``airflow.sdk`` cannot be imported here
without a scheduler in the picture, so anything testable at this seam had to be
written to not need one. The DAG files are left as wiring.

The function names here are the module's public names. They were private
(``_fetch_orders``) and imported out of a DAG file, which is what an extraction
shared by two DAGs forced into existence: ``dags/pipeline/orders_extract.py`` now
holds the logic and both DAGs are wrappers over it.
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from dags.pipeline.intervals import NIGHTLY_SCHEDULE
from dags.pipeline.orders_extract import fetch_orders, select_window, upsert_orders


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


class FakeCursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple | None]] = []

    def execute(self, statement: str, parameters: tuple | None = None) -> None:
        self.calls.append((statement, parameters))


class OrdersIngestionTests(unittest.TestCase):
    def test_window_prefers_complete_run_configuration(self) -> None:
        start, end = select_window(
            {"created_after": "2026-02-01T00:00:00-05:00", "created_before": "2026-02-02T00:00:00-05:00"},
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 2, tzinfo=timezone.utc),
        )

        self.assertEqual(start, "2026-02-01T05:00:00Z")
        self.assertEqual(end, "2026-02-02T05:00:00Z")

    def test_window_uses_airflow_interval_without_run_configuration(self) -> None:
        start, end = select_window(
            {},
            datetime(2026, 3, 1, tzinfo=timezone.utc),
            datetime(2026, 3, 2, tzinfo=timezone.utc),
        )

        self.assertEqual((start, end), ("2026-03-01T00:00:00Z", "2026-03-02T00:00:00Z"))

    def test_half_specified_window_is_rejected_rather_than_guessed(self) -> None:
        # The failure this prevents is silent and total: one bound given, one
        # defaulted, means extracting the whole universe on the open side.
        with self.assertRaises(ValueError):
            select_window(
                {"created_after": "2026-03-01T00:00:00Z"},
                datetime(2026, 3, 1, tzinfo=timezone.utc),
                datetime(2026, 3, 2, tzinfo=timezone.utc),
            )

    def test_naive_window_bound_is_rejected(self) -> None:
        # The source rejects a naive timestamp, so accepting one here would defer
        # the failure to a place with no idea what the operator meant.
        with self.assertRaises(ValueError):
            select_window(
                {}, datetime(2026, 3, 1), datetime(2026, 3, 2, tzinfo=timezone.utc)
            )

    def test_nightly_interval_is_the_day_that_ended(self) -> None:
        """The run labelled 2026-03-02 must extract 2026-03-01.

        This is a regression test for a failure that cost a scheduled run. In
        Airflow 3 a bare `schedule="@daily"` resolves to `CronTriggerTimetable`,
        whose data interval is a single instant - [2026-03-02, 2026-03-02) - so
        every nightly run raised `created_after must be earlier than created_before`
        before reading a row, while manually triggered runs (which take their
        window from `conf`) passed and hid it. The assertion above, which reads
        the interval as the window, is only true for a timetable that produces an
        interval; this is the test that says so directly.
        """
        interval = NIGHTLY_SCHEDULE.infer_manual_data_interval(
            run_after=datetime(2026, 3, 2, tzinfo=timezone.utc)
        )

        self.assertEqual(
            (interval.start, interval.end),
            (
                datetime(2026, 3, 1, tzinfo=timezone.utc),
                datetime(2026, 3, 2, tzinfo=timezone.utc),
            ),
        )

    def test_fetches_every_page_with_the_same_requested_window(self) -> None:
        responses = [
            {"data": [{"order_id": "one"}], "meta": {"page": 1, "has_next": True, "next_page": 2}},
            {"data": [{"order_id": "two"}], "meta": {"page": 2, "has_next": False, "next_page": None}},
        ]
        urls: list[str] = []

        def fake_urlopen(url: str, timeout: int) -> FakeResponse:
            urls.append(url)
            self.assertEqual(timeout, 30)
            return FakeResponse(responses.pop(0))

        with patch("dags.pipeline.orders_extract.urlopen", side_effect=fake_urlopen):
            orders = fetch_orders(
                "http://orders-api:8000/", "2026-03-01T00:00:00Z", "2026-03-02T00:00:00Z"
            )

        self.assertEqual([order["order_id"] for order in orders], ["one", "two"])
        self.assertEqual(len(urls), 2)
        for page, url in enumerate(urls, start=1):
            query = parse_qs(urlparse(url).query)
            self.assertEqual(query["created_after"], ["2026-03-01T00:00:00Z"])
            self.assertEqual(query["created_before"], ["2026-03-02T00:00:00Z"])
            self.assertEqual(query["page"], [str(page)])

    def test_pagination_stops_on_a_backwards_next_page(self) -> None:
        # A source that pointed next_page at a page already visited would spin
        # this loop forever rather than fail, so the visited set is load-bearing.
        responses = [
            {"data": [{"order_id": "one"}], "meta": {"page": 1, "has_next": True, "next_page": 1}},
        ]
        with patch(
            "dags.pipeline.orders_extract.urlopen",
            side_effect=lambda url, timeout: FakeResponse(responses.pop(0)),
        ):
            with self.assertRaises(ValueError):
                fetch_orders("http://orders-api:8000/", "2026-03-01T00:00:00Z", "2026-03-02T00:00:00Z")

    def test_upsert_uses_order_identity_and_serializes_items(self) -> None:
        cursor = FakeCursor()
        order = {
            "order_id": "order-1",
            "customer_id": "customer-1",
            "status": "placed",
            "currency": "USD",
            "total_cents": 1200,
            "items": [{"sku": "sku-1", "quantity": 1, "unit_price_cents": 1200}],
            "created_at": "2026-03-01T00:00:00Z",
            "ingested_at": "2026-03-01T00:00:00Z",
            "updated_at": "2026-03-01T00:00:00Z",
            "version": 1,
        }

        upsert_orders(cursor, [order])

        self.assertIn("order_id       text PRIMARY KEY", cursor.calls[0][0])
        statement, parameters = cursor.calls[1]
        self.assertIn("ON CONFLICT (order_id) DO UPDATE", statement)
        self.assertEqual(parameters[0], "order-1")
        self.assertEqual(json.loads(parameters[5]), order["items"])


if __name__ == "__main__":
    unittest.main()