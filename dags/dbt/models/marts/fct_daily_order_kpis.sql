-- Mart: one row per business day, the table the course's pipeline exists to
-- produce.
--
-- Everything above this file decides what a number means; this file only sums
-- it. Two things are worth reading carefully anyway:
--
--   * `filter (where ...)` rather than `sum(case when ... then 1 else 0 end)`.
--     Both are correct; the filter form counts and sums in one pass and, in
--     Postgres, returns 0 rather than NULL for a day with no orders of that
--     kind. A KPI column that is NULL means "we did not measure"; a KPI column
--     that is 0 means "there were none", and those are different sentences.
--
--   * `nullif(net_orders, 0)` in the average. A day with no net orders has no
--     average order value, and saying so with NULL is the honest answer.
--     Postgres's `round` on numeric rounds halves away from zero, which is what
--     the pipeline assertion's independent expectation does with Decimal's
--     ROUND_HALF_UP - the two agree by construction, not by luck.

select
    order_date,
    count(*)                                                     as orders_total,
    count(distinct customer_id)                                  as customers_total,
    sum(units_total)                                             as units_total,
    sum(line_count)                                              as line_items_total,
    sum(total_cents)                                             as gross_merchandise_cents,
    count(*) filter (where counts_as_net_sale)                   as net_orders,
    coalesce(
        sum(total_cents) filter (where counts_as_net_sale), 0
    )                                                            as net_merchandise_cents,
    count(*) filter (where status = 'cancelled')                 as cancelled_orders,
    count(*) filter (where status = 'returned')                  as returned_orders,
    cast(
        round(
            coalesce(
                sum(total_cents) filter (where counts_as_net_sale), 0
            )::numeric
            / nullif(count(*) filter (where counts_as_net_sale), 0)
        ) as bigint
    )                                                            as net_average_order_value_cents
from {{ ref('int_orders_enriched') }}
group by order_date
