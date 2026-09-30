-- Staging: one row per extracted order, renamed and retyped, with nothing
-- decided. A staging model exists to make the warehouse's own types explicit
-- so that no model above it has to guess, and to insulate them from a change in
-- how the extract table is shaped.
--
-- It decides nothing: no business date, no flags, no aggregation. Those belong
-- to the intermediate layer, where the reasoning is visible.

select
    order_id::text          as order_id,
    customer_id::text       as customer_id,
    status::text            as status,
    currency::text          as currency,
    total_cents::integer    as total_cents,
    items::jsonb            as items,
    created_at::timestamptz as created_at,
    ingested_at::timestamptz as ingested_at,
    updated_at::timestamptz as updated_at,
    version::integer        as version
from {{ source('raw', 'orders') }}
