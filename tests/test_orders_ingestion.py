from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from dags.pipeline.orders_ingestion import _fetch_orders, _select_window, _upsert_orders


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
        start, end = _select_window(
            {"created_after": "2026-02-01T00:00:00-05:00", "created_before": "2026-02-02T00:00:00-05:00"},
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 2, tzinfo=timezone.utc),
        )

        self.assertEqual(start, "2026-02-01T05:00:00Z")
        self.assertEqual(end, "2026-02-02T05:00:00Z")

    def test_window_uses_airflow_interval_without_run_configuration(self) -> None:
        start, end = _select_window(
            {},
            datetime(2026, 3, 1, tzinfo=timezone.utc),
            datetime(2026, 3, 2, tzinfo=timezone.utc),
        )

        self.assertEqual((start, end), ("2026-03-01T00:00:00Z", "2026-03-02T00:00:00Z"))

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

        with patch("dags.pipeline.orders_ingestion.urlopen", side_effect=fake_urlopen):
            orders = _fetch_orders(
                "http://orders-api:8000/", "2026-03-01T00:00:00Z", "2026-03-02T00:00:00Z"
            )

        self.assertEqual([order["order_id"] for order in orders], ["one", "two"])
        self.assertEqual(len(urls), 2)
        for page, url in enumerate(urls, start=1):
            query = parse_qs(urlparse(url).query)
            self.assertEqual(query["created_after"], ["2026-03-01T00:00:00Z"])
            self.assertEqual(query["created_before"], ["2026-03-02T00:00:00Z"])
            self.assertEqual(query["page"], [str(page)])

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

        _upsert_orders(cursor, [order])

        self.assertIn("order_id       text PRIMARY KEY", cursor.calls[0][0])
        statement, parameters = cursor.calls[1]
        self.assertIn("ON CONFLICT (order_id) DO UPDATE", statement)
        self.assertEqual(parameters[0], "order-1")
        self.assertEqual(json.loads(parameters[5]), order["items"])


if __name__ == "__main__":
    unittest.main()