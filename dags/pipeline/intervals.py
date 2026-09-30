"""What a nightly run's window actually is.

One timetable, declared once, because the choice between two Airflow 3 cron
timetables decides whether a nightly DAG works at all and the reason is not
guessable from the DAG file.

``schedule="@daily"`` in Airflow 3 resolves to `CronTriggerTimetable`. Its data
interval is a single instant: the run labelled 2026-10-01 has the interval
[2026-10-01, 2026-10-01). That is the right shape for "wake me at midnight" and
the wrong shape for "extract the day that just ended" - `select_window` rejects
a window that is not strictly forward, so every nightly run fails with
`created_after must be earlier than created_before` before a single row is read.
The failure is silent until a scheduled run happens; a manually triggered run
with both bounds in its `conf` never touches the data interval and passes.

`CronDataIntervalTimetable` triggers at the same midnight and gives the interval
[2026-09-30, 2026-10-01), so the run labelled 2026-10-01 extracts 2026-09-30.
`tests/test_orders_ingestion.py` asserts that reading the interval is how a run
without a run configuration picks its window; this is the timetable that makes
that assertion true.

The timezone is pinned to UTC for the same reason the dbt models say
`at time zone 'utc'`: a window whose bounds are computed in the machine's local
zone is a different window on every machine, which makes a pipeline that cannot
be reproduced.
"""

from __future__ import annotations

from airflow.timetables.interval import CronDataIntervalTimetable

NIGHTLY_SCHEDULE = CronDataIntervalTimetable("0 0 * * *", timezone="UTC")