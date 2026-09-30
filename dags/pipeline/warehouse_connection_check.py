"""First hand-written DAG of the continuous project: prove the feedback loop.

This DAG exists to close the loop that every later lesson depends on — that
Airflow can be told apart from the environment it runs in. It reads the course
warehouse's credential from the Airflow connection store, connects to the
warehouse, and round-trips one row.

The secrets boundary is the point of the exercise, so note what is *not* here:
no host, no port, no database, no role, no password. Every one of those arrives
through ``Connection.get(WAREHOUSE_CONN_ID)``, which talks to Airflow over the
Execution API. The file names a connection id, exactly as it would name a
colleague.
"""

from __future__ import annotations

from datetime import datetime

import psycopg2
from airflow.sdk import Connection, dag, task

# The only piece of the warehouse's location this file is allowed to know.
# It is an Airflow-side name for a credential, not a secret.
WAREHOUSE_CONN_ID = "warehouse_default"

_CHECK_NAME = "warehouse_connection_check"


@dag(
    dag_id="pipeline_warehouse_connection_check",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["pipeline", "foundation"],
)
def pipeline_warehouse_connection_check():
    @task(task_id="resolve_warehouse_endpoint")
    def resolve_warehouse_endpoint() -> dict:
        """Look the credential up in the connection store.

        Reports where the warehouse is, never what authenticates to it. The
        password is fetched but deliberately not returned: this value is
        pushed to XCom, which is stored in the metadata database and rendered
        in the task UI. Anything returned here is a published value.
        """
        conn = Connection.get(WAREHOUSE_CONN_ID)
        return {
            "conn_id": conn.conn_id,
            "conn_type": conn.conn_type,
            "host": conn.host,
            "port": conn.port,
            "database": conn.schema,
            "login": conn.login,
            "password_suppressed": bool(conn.password),
        }

    @task(task_id="warehouse_round_trip")
    def warehouse_round_trip(endpoint: dict) -> dict:
        """Create a table in the warehouse, write a row, read it back.

        Takes the resolved endpoint only as evidence that the upstream task
        ran. It re-reads the connection itself rather than receiving
        credentials over XCom, so the secret never travels between tasks.
        """
        conn = Connection.get(WAREHOUSE_CONN_ID)
        with psycopg2.connect(
            host=conn.host,
            port=conn.port,
            dbname=conn.schema,
            user=conn.login,
            password=conn.password,
        ) as db:
            with db.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS pipeline_health_check (
                        check_name      text PRIMARY KEY,
                        endpoint        text        NOT NULL,
                        connected_as    text        NOT NULL,
                        checked_at      timestamptz NOT NULL DEFAULT now()
                    )
                    """
                )
                # Upsert, not insert: re-running the DAG must not fail on a
                # duplicate key. Idempotence is the property the primary test
                # seam asserts, so it starts with the first table.
                cur.execute(
                    """
                    INSERT INTO pipeline_health_check (check_name, endpoint, connected_as)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (check_name) DO UPDATE
                        SET endpoint     = EXCLUDED.endpoint,
                            connected_as = EXCLUDED.connected_as,
                            checked_at   = now()
                    """,
                    (
                        _CHECK_NAME,
                        f"{conn.host}:{conn.port}/{conn.schema}",
                        conn.login,
                    ),
                )
                cur.execute(
                    """
                    SELECT check_name, endpoint, connected_as, checked_at
                    FROM pipeline_health_check
                    WHERE check_name = %s
                    """,
                    (_CHECK_NAME,),
                )
                check_name, row_endpoint, connected_as, checked_at = cur.fetchone()
            server_version = db.get_parameter_status("server_version")

        return {
            "resolved_by": endpoint["conn_id"],
            "server": server_version,
            "row": {
                "check_name": check_name,
                "endpoint": row_endpoint,
                "connected_as": connected_as,
                "checked_at": checked_at.isoformat(),
            },
        }

    endpoint = resolve_warehouse_endpoint()
    warehouse_round_trip(endpoint)


pipeline_warehouse_connection_check()
