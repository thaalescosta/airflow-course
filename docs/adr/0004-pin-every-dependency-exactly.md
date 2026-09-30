# Every dependency is pinned exactly, and upgrades are taught

Requirements and the image tag are pinned to exact versions, including where a newer patch exists (Astro Runtime 3.3-7, which is Airflow 3.3.1, not 3.3.2). Floating ranges are rejected because the failure mode is silent and total: `astronomer-cosmos` between 1.5.1 and 1.13.1 crashes the entire Airflow process on Airflow 3.2/3.3 with a circular import in `cosmos/settings.py`, and 1.15.0 shipped a Kubernetes operator ENTRYPOINT change that 1.15.1 reverted. The working range is therefore `>=1.15.1,<1.16`.

Because the pins are hard, moving them is course content rather than maintenance. Each upgrade is its own lesson: read the changelog, find the breaking change, reproduce it, and record it.
