FROM python:3.12.11-slim-bookworm

WORKDIR /workspace

RUN apt-get update \
	&& apt-get install --no-install-recommends --yes git=1:2.39.5-0+deb12u3 \
	&& rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/dbt-requirements.txt
RUN pip install --no-cache-dir --requirement /tmp/dbt-requirements.txt

COPY entrypoint.sh /usr/local/bin/dbt-entrypoint
ENTRYPOINT ["/bin/sh", "/usr/local/bin/dbt-entrypoint"]
CMD ["dbt", "--help"]