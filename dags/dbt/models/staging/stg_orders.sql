select
    order_id,
    customer_id,
    status,
    currency,
    total_cents,
    items,
    created_at,
    ingested_at,
    updated_at,
    version
from {{ source('raw', 'orders') }}