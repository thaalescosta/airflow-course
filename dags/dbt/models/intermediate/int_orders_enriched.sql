-- Intermediate: one row per order, with the business date resolved and the
-- line items rolled up to the order's own grain.
--
-- This model is where the pipeline's business rules are written down, once.
-- Two rules, both visible here and nowhere else:
--
--   1. The business date is the UTC calendar date of `created_at` - the day the
--      customer placed the order, not the day the source published it and not
--      the day the order was last corrected. A late arrival therefore lands on
--      the day it belongs to, which is the only placement that makes a daily
--      series add up.
--
--   2. An order that is `cancelled` or `returned` did not produce revenue.
--      Whether that is true of your business is a question only you can answer;
--      here it is one named flag, so a disagreement about the KPI numbers can
--      be settled by changing one line here rather than by rewriting the mart.
--
-- Everything downstream is arithmetic over these two decisions. That is the
-- argument for the intermediate layer existing: the mart says what it reports,
-- this model says what it means.

with item_rollup as (

    select
        order_id,
        count(*)  as line_count,
        sum(quantity) as units_total
    from {{ ref('stg_order_items') }}
    group by order_id

), orders as (

    select * from {{ ref('stg_orders') }}

)

select
    orders.order_id,
    orders.customer_id,
    orders.status,
    orders.currency,
    orders.total_cents,
    orders.version,
    orders.created_at,
    (orders.created_at at time zone 'utc')::date        as order_date,
    coalesce(item_rollup.line_count, 0)                 as line_count,
    coalesce(item_rollup.units_total, 0)                as units_total,
    orders.status in ('cancelled', 'returned')          as is_reversed,
    orders.status not in ('cancelled', 'returned')      as counts_as_net_sale
from orders
left join item_rollup
    on item_rollup.order_id = orders.order_id
