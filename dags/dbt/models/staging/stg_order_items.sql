-- Staging: one row per extracted order, with the source's jsonb turned into
-- rows and the business date resolved.
--
-- The flattening is staging's job, not the mart's. `raw.orders` stores the line
-- items as one jsonb array because that is how the source publishes them; every
-- model above this one wants them the other shape. Doing the unnesting once
-- here means the intermediate and the mart never repeat it and never disagree
-- about how it was done.
--
-- Order-level columns ride along with the item rows because the unnesting is a
-- lateral join: without them, every downstream model would have to join back to
-- stg_orders to learn which day or which status a line belongs to.
--
-- `at time zone 'utc'` is not decoration. Casting a timestamptz straight to
-- date resolves against the session's TimeZone setting, so the same model would
-- produce a different business date on a machine configured for anywhere else,
-- and a daily KPI table that moves when the container does is not a KPI table.
-- Naming the zone makes the cast total.

with orders as (

    select * from {{ ref('stg_orders') }}

), lines as (

    select
        orders.order_id,
        orders.customer_id,
        orders.status,
        orders.currency,
        (orders.created_at at time zone 'utc')::date as order_date,
        line.item ->> 'sku'                            as sku,
        (line.item ->> 'quantity')::integer             as quantity,
        (line.item ->> 'unit_price_cents')::integer     as unit_price_cents,
        (line.item ->> 'quantity')::integer
            * (line.item ->> 'unit_price_cents')::integer as line_total_cents
    from orders
    cross join lateral jsonb_array_elements(orders.items) as line (item)

)

select * from lines
