set -eu

if [ -r /run/secrets/warehouse_pg_password ]; then
	export DBT_ENV_SECRET_WAREHOUSE_PASSWORD="$(cat /run/secrets/warehouse_pg_password)"
fi

exec "$@"