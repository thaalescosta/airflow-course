set -eu

# The warehouse password is mounted read-only at /run/secrets and never baked
# into the image or the project files, so the standalone dbt CLI picks it up
# from the same secret the Airflow stack does. CRLF in this file would make
# `set -eu` an illegal option; .gitattributes at the repository root exists so
# that does not happen on a Windows checkout.
if [ -r /run/secrets/warehouse_pg_password ]; then
	export DBT_ENV_SECRET_WAREHOUSE_PASSWORD="$(cat /run/secrets/warehouse_pg_password)"
fi

exec "$@"
