# Orders API contract (frozen)

This is the course-side record of the wire schema served by `GET /orders`. The
canonical model definitions live in the sibling API project at
`../orders-api/app/schemas.py` (relative to the course repository root); that
file is the source of truth. This document records the same contract for
readers working in the course repository. It is not a second schema to evolve
independently.

- API contract: `orders-api/1.0.0`
- Schema version: `1.0.0`
- Frozen on: 2026-09-30
- Breaking changes are deferred to the deliberate fixture break in issue #28.

A change to a field name, type, nullability, constraint, or response shape
invalidates lessons written against this contract. Update this record only when
the canonical API schema changes as part of that deliberate break.

## `GET /orders`

The response is an envelope, not a bare array:

```json
{
  "data": [
    {
      "order_id": "string",
      "customer_id": "string",
      "status": "placed",
      "currency": "string",
      "total_cents": 0,
      "items": [
        {
          "sku": "string",
          "quantity": 1,
          "unit_price_cents": 0
        }
      ],
      "created_at": "2026-01-01T00:00:00Z",
      "ingested_at": "2026-01-01T00:00:00Z",
      "updated_at": "2026-01-01T00:00:00Z",
      "version": 1
    }
  ],
  "meta": {
    "page": 1,
    "page_size": 100,
    "total_items": 1,
    "total_pages": 1,
    "has_next": false,
    "next_page": null
  },
  "query": {
    "created_after": null,
    "created_before": null,
    "as_of": "2026-07-01T00:00:00Z",
    "page": 1,
    "page_size": 100
  }
}
```

The values above illustrate JSON types and shape; example order values are not
fixture guarantees. All fields shown are present in the response. The two
window fields in `query` are nullable and are emitted as `null` when omitted.
Datetime values are ISO-8601 strings; the deterministic test pins the default
`query.as_of` serialization to `2026-07-01T00:00:00Z`.

### Fields

| Object | Field | Wire type | Constraint or meaning |
| --- | --- | --- | --- |
| `data[]` | `order_id` | string | Order identifier |
| `data[]` | `customer_id` | string | Customer identifier |
| `data[]` | `status` | string enum | `placed`, `paid`, `packed`, `shipped`, `delivered`, `cancelled`, or `returned` |
| `data[]` | `currency` | string | Currency code |
| `data[]` | `total_cents` | integer | At least 0; money is represented in integer cents |
| `data[]` | `items` | array of `LineItemResponse` | Order line items |
| `data[].items[]` | `sku` | string | SKU |
| `data[].items[]` | `quantity` | integer | At least 1 |
| `data[].items[]` | `unit_price_cents` | integer | At least 0; money is represented in integer cents |
| `data[]` | `created_at` | datetime string | Business creation time |
| `data[]` | `ingested_at` | datetime string | Time the source published the row |
| `data[]` | `updated_at` | datetime string | Time of the current order version |
| `data[]` | `version` | integer | At least 1; increments once per correction |
| `meta` | `page` | integer | 1-based page number; at least 1 |
| `meta` | `page_size` | integer | At least 1 |
| `meta` | `total_items` | integer | At least 0; count after filtering and before page slicing |
| `meta` | `total_pages` | integer | At least 0; computed from the full filtered result set |
| `meta` | `has_next` | boolean | Whether another page exists |
| `meta` | `next_page` | integer or null | Next 1-based page, or `null` when there is no next page |
| `query` | `created_after` | datetime string or null | Inclusive lower bound on `created_at` |
| `query` | `created_before` | datetime string or null | Exclusive upper bound on `created_at` |
| `query` | `as_of` | datetime string | Observation time; defaults to constant `2026-07-01T00:00:00Z`, not the wall clock |
| `query` | `page` | integer | Resolved page number |
| `query` | `page_size` | integer | Resolved page size |

All listed fields are required in their containing object. `created_after`,
`created_before`, and `next_page` permit `null`; the other fields do not.

### Query and pagination behavior

- `created_after` and `created_before` accept RFC 3339 timestamps with an
  explicit timezone offset. The window is half-open: `[created_after,
  created_before)`. Either bound may be omitted; when both are provided, the
  lower bound must be earlier than the upper bound.
- `as_of` accepts an RFC 3339 timestamp with an explicit offset. If omitted, it
  resolves to the fixed `WORLD_END` (`2026-07-01T00:00:00Z`).
- `page` is 1-based and defaults to `1`.
- `page_size` defaults to `100` and is limited to `1` through `1000`.
- Filtering is by `created_at` at the requested `as_of`. Pagination is then
  applied to the complete filtered result set. `total_items` and
  `total_pages` do not depend on the requested page; a page past the end has an
  empty `data` array.
- `version` starts at `1` and increments once for each scheduled correction.
  `ingested_at` exposes late arrival separately from `created_at`.

## Source mapping

The response models are `LineItemResponse`, `OrderResponse`,
`PaginationMeta`, `ResolvedQuery`, and `OrdersPageResponse` in the canonical
API `../orders-api/app/schemas.py`. The endpoint defaults, query validation,
filtering, and pagination are implemented by `GET /orders` in
`../orders-api/app/main.py`. These paths are relative to the course repository
root. This course-side record must remain aligned with those implementations.
