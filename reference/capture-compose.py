"""Materialise the effective compose configuration of a running astro dev stack.

The Astro CLI generates its compose model in memory and never writes a
docker-compose.yml to disk, so this captures the resolved configuration from
`docker inspect` instead. Re-run with the stack up to refresh the artifact.
"""

import json
import subprocess
import sys

PROJECT = "airflow-course_d896a3"
KEEP_ENV_PREFIX = ("AIRFLOW__", "POSTGRES_", "ASTRO_", "_AIRFLOW")


def sh(args):
    return subprocess.run(
        args, capture_output=True, text=True, check=True
    ).stdout


names = sh(
    [
        "docker", "ps", "-a",
        "--filter", f"label=com.docker.compose.project={PROJECT}",
        "--format", "{{.Names}}",
    ]
).split()

docs = json.loads(sh(["docker", "inspect", *names]))
docs.sort(key=lambda d: d["Config"]["Labels"]["com.docker.compose.service"])

services = {}
for d in docs:
    cfg, host, lbl = d["Config"], d["HostConfig"], d["Config"]["Labels"]
    env = {
        e.split("=", 1)[0]: e.split("=", 1)[1]
        for e in cfg.get("Env", [])
        if e.split("=", 1)[0].startswith(KEEP_ENV_PREFIX)
    }
    ports = {}
    for cp, binds in (host.get("PortBindings") or {}).items():
        for b in binds:
            ports[f"{cp.split('/')[0]}/{b.get('HostIp', '0.0.0.0')}"] = int(
                b["HostPort"]
            )
    services[lbl["com.docker.compose.service"]] = {
        "container_name": d["Name"].lstrip("/"),
        "image": cfg["Image"],
        "state": d["State"]["Status"],
        "user": cfg.get("User") or None,
        "command": cfg.get("Cmd") or None,
        "entrypoint": cfg.get("Entrypoint") or None,
        "environment": env,
        "ports": ports or None,
        "working_dir": cfg.get("WorkingDir") or None,
        "volumes": [
            {
                "type": v["Type"],
                "source": v["Source"],
                "destination": v["Destination"],
                "read_only": not v.get("RW", True),
            }
            for v in d.get("Mounts", [])
        ]
        or None,
        "depends_on": [
            k[len("service_depends_on_"):]
            for k in lbl
            if k.startswith("service_depends_on_")
        ]
        or None,
        "restart_policy": {
            "name": host.get("RestartPolicy", {}).get("Name"),
            "max_retries": host.get("RestartPolicy", {}).get("MaximumRetryCount"),
        },
        "shm_size": host.get("ShmSize"),
        "config_hashes": lbl.get("com.docker.compose.config-hash"),
    }

out = {
    "_generated_by": "reference/capture-compose.py (see reference/environment-baseline.md)",
    "_note": (
        "Effective compose configuration recovered from the running containers. "
        "The Astro CLI does not persist a compose file to disk."
    ),
    "project": PROJECT,
    "compose_spec": "https://github.com/compose-spec/compose-spec",
    "services": services,
    "x-astro-image-labels": {
        k: v
        for k, v in json.loads(
            sh(
                [
                    "docker", "image", "inspect",
                    f"{PROJECT}/airflow:latest", "--format", "{{json .Config.Labels}}",
                ]
            )
        ).items()
        if k.startswith("io.astronomer.docker")
    },
}

json.dump(out, sys.stdout, indent=2, sort_keys=False)
print()
