# The primary seam: the pipeline assertion

The course's four test seams are listed in `AGENTS.md`. This file says which one
is load-bearing, what "correct" means at that seam, and — the part that is easy to
get wrong — how each later module is supposed to be verified.

## The one command

From the repository root:

```sh
.venv/Scripts/python tests/assert_pipeline_kpis.py
```

It is the whole test suite for the continuous project. There is no second command
to remember, no marker to select, no fixture to install. If it exits 0, the
pipeline is correct over its window, twice, unchanged.

It is also the onboarding gate, in the order the environment actually fails:

| Step | Checks | Why it is here |
| --- | --- | --- |
| 1 Environment up | seven compose services running, all four Airflow components heartbeating, the warehouse secret present, `warehouse_default` seeded | The layers below are meaningless against a container that is not there. |
| 2 Cosmos importable | `import cosmos` **in the dag-processor**, and the running version matches the pin in `requirements.txt` | Checked in the component that parses DAGs, not on the host. An import that works on the host and fails in the dag-processor is exactly the false negative this step exists to prevent. |
| 3 dbt executable | `dbt --version` **in the scheduler**, and the running core matches the pin | Checked where `ExecutionMode.LOCAL` actually shells out. A dbt that imports but is not on `PATH` passes every import check and fails every model task. |
| 4 Data source reachable | DNS for `orders-api` and a real `/health` **from inside the scheduler** | The pipeline reaches the API by service name over the container network (ADR 0005). Proving that from the host over a published port would prove a different thing. |
| 5 A first DAG parses | zero import errors, and the rendered graph is listed | `astro dev parse` is the same check; this one prints the nine tasks so Cosmos's rendering is visible rather than inferred. |
| 6 The assertion | the rest of this file | |

## What "correct" means here

The pipeline runs twice over `[2026-02-01T00:00:00Z, 2026-06-15T00:00:00Z)`, and
the assertion checks three things.

**The KPIs are right.** `analytics_marts.fct_daily_order_kpis` is compared
day by day, column by column, against values computed in Python from the orders
API. The expectation does not consult a dbt model, a staging view, or the
warehouse. It is a second implementation of the same business rules in a different
language, reached over a different transport (HTTP from outside the stack, versus
`http://orders-api:8000` from inside it) at a different page size (500, versus the
extraction's 1000). When the two disagree, one of them is wrong, and the
disagreement is the finding.

**The pipeline is idempotent.** The second run must leave the warehouse in exactly
the state the first did: the same rows, the same totals, the same row count in the
extract table, and a byte-identical `kpi_digest`. An extraction that appended
instead of upserting, or a model that accumulated, doubles here.

**The run did what it was asked.** Two checks read Airflow's state rather than the
warehouse, because two of the pipeline's claims are not visible in its output. The
run's task instances must include a task for each dbt model Cosmos is specified to
render — a model skipped in the graph still leaves a correct table if an earlier
run built it. And the extraction task's own report of the window it read must match
the window that was requested, because two runs differ in their logical dates and
that must not matter.

## The one rule at this seam

The assertion asserts externally observable behaviour. It reads the warehouse and
Airflow's report of the run it triggered. It does not import a pipeline module, read
a DAG file, or search a source file for a string.

The reason is that the pipeline can be renamed into passing otherwise. Assert that
`fct_daily_order_kpis` is spelled that way, or that the intermediate model contains
`counts_as_net_sale`, and the assertion survives a rewrite of the thing it was
supposed to be checking. It fails on the day someone fixes a bug in a way that moves
a number, and stays green on the day someone breaks a number by renaming a column.

`tests/test_orders_ingestion.py` is where the rule does not apply, and that is not a
contradiction. Those tests call pure functions directly and assert what they return
and what SQL they emit; there is no pipeline there to rename, and
`ON CONFLICT (order_id) DO UPDATE` is genuinely part of the contract with the
database. The rule scopes a *whole-pipeline* assertion. It does not make unit tests
of a warehouse boundary taboos.

## How later modules extend it

**They extend it. They do not add a second assertion.**

A module that arrives after this one does not get its own end-to-end check. It gets
added to the one that is already here, and the existing command's output changes
because the pipeline now does more. Concretely, a later module adds:

- **a model** — it appears in `DBT_MODELS`, and Cosmos's rendering of it is checked
  automatically because the list is checked.
- **a column on the mart** — it appears in `KPI_COLUMNS`, and the comparison
  extends. The expectation has to compute it too, which is the cost: a new column
  is only asserted once it is stated twice, in two languages.
- **a new day in the window** — nothing changes, which is the point of choosing a
  window rather than hard-coding today's date.
- **a second source, a new table, a new upstream** — the gate grows by one step, in
  the same order, before the assertion runs.

The test to apply to any proposed new check: *if this broke, would the pipeline
still be wrong in a way a reader would care about?* If yes, it belongs here. If the
answer is only "the test would fail", it belongs at one of the other three seams.

A new **seam** is a different question and needs its own answer. Seams 1, 2 and 4
exist because they catch things the pipeline assertion cannot see: a DAG that will
not parse, a pagination loop that spins, a not-null test that does not run.

## What a failure looks like

The assertion prints the day, the column, and both values, and stops at the first
run. Measured, by deliberately changing the net-sale rule in
`dags/dbt/models/intermediate/int_orders_enriched.sql` so that only `cancelled`
orders are excluded:

```
  first run kpi_digest               52c05595c477e2fe…      (expected 358e0599f8514dcd…)

KPI MISMATCH after run 1:
  2026-02-01 net_orders: expected 8, warehouse has 9
  2026-02-01 net_merchandise_cents: expected 127460, warehouse has 135260
  2026-02-01 net_average_order_value_cents: expected 15933, warehouse has 15029
  2026-02-07 net_orders: expected 4, warehouse has 7
  … and 41 more
```

Two things worth reading off that output. It names the rule that changed rather than
a file, because only the columns that rule governs moved: `cancelled_orders` and
`returned_orders` stayed correct, and `gross_merchandise_cents` never appeared. And
it stopped after run 1 — a wrong number is not worth confirming twice.

## The window, and why it is that window

Chosen, not arbitrary, and re-choosing it is a decision with three parts:

- **134 business days, 1116 orders.** Large enough that the source's pagination is
  walked for real at both page sizes, so the envelope is exercised rather than
  assumed.
- **A strict subset in both directions.** Orders exist before 2026-02-01 and after
  2026-06-15, so a pipeline that dropped a bound or sent the window unreduced
  produces days outside the window, and `compare()` reports them as such.
- **Midnight UTC on both ends.** The bounds are exercised at a boundary rather
  than in the middle of a day, and the timezone is explicit everywhere so the window
  is the same window on every machine.

The expected `kpi_digest` for this window is
`358e0599f8514dcd6d0ef8dd62e51465e9a84ebdbe53d43877c9143a1fd5416d`. If that changes
without the window changing, something is wrong — that string is the assertion's
answer to "is this deterministic", and it is only evidence because it is stable.