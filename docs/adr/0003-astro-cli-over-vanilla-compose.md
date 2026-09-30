# Astro CLI, not a hand-written compose file

Local Airflow runs through `astro dev start` rather than a hand-written `docker-compose.yaml`. This is a deliberate trade: the CLI makes setup one command, which is the right trade while the learner is still learning Airflow, but it hides the deployment shape, ships Airflow 3.3.1 via Runtime 3.3-7 rather than 3.3.2, and hardcodes LocalExecutor with no flag to change it.

Two consequences are accepted rather than hidden. The first lesson reads the generated `Dockerfile` and compose output as an artifact to be understood rather than consumed, and a later lesson rebuilds a minimal vanilla compose by hand so the learner owns the shape they were shielded from. Cosmos stays a thin, replaceable layer over that shape: it is Apache-2.0 and pip-installed, so moving to a plain `apache/airflow` image is a `FROM` line change plus a requirements file.
