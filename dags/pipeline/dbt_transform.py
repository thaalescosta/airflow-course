"""Run the course dbt project as Cosmos tasks inside a hand-written DAG."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from airflow.sdk import dag, task
from cosmos import DbtTaskGroup, ExecutionConfig, ProfileConfig, ProjectConfig
from cosmos.constants import ExecutionMode
from cosmos.profiles import PostgresUserPasswordProfileMapping

WAREHOUSE_CONN_ID = "warehouse_default"
DBT_PROJECT_PATH = Path(__file__).resolve().parents[1] / "dbt"

profile_config = ProfileConfig(
    profile_name="airflow_course",
    target_name="local",
    profile_mapping=PostgresUserPasswordProfileMapping(
        conn_id=WAREHOUSE_CONN_ID,
        profile_args={"schema": "analytics", "threads": 4},
        disable_event_tracking=True,
    ),
)


@dag(
    dag_id="pipeline_dbt_transform",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["pipeline", "dbt", "cosmos"],
    description="Run the dbt project in Cosmos between hand-written DAG tasks.",
)
def pipeline_dbt_transform():
    @task(task_id="start_dbt_pipeline")
    def start_dbt_pipeline() -> None:
        pass

    @task(task_id="finish_dbt_pipeline")
    def finish_dbt_pipeline() -> None:
        pass

    dbt_project = DbtTaskGroup(
        group_id="cosmos_dbt_project",
        project_config=ProjectConfig(DBT_PROJECT_PATH),
        profile_config=profile_config,
        execution_config=ExecutionConfig(
            execution_mode=ExecutionMode.LOCAL,
        ),
    )

    start_dbt_pipeline() >> dbt_project >> finish_dbt_pipeline()


pipeline_dbt_transform()