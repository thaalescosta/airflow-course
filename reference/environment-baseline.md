# Environment baseline (verified)

Everything in this file was measured on the course machine, not read from a
document. It is the reference a lesson cites when it needs to say "this is what
the environment actually does". Re-verify rather than trust: the commands are
given so the numbers can be regenerated.

Measured on 2026-09-30. Host: Windows 11, git-bash, not elevated.

## 1. Cold start

Two phases. The first is once per machine; the second is once per clone. Run both
in a **Windows shell** — Windows PowerShell or git-bash. Not a WSL terminal, not
an elevated shell.

```sh
# Phase 1 — once per machine. --skip-dependencies is load-bearing: from CLI
# 1.32.0 the default install drags in Podman as the container engine. We want
# the Docker runtime that is already on the box.
winget install -e --id Astronomer.Astro -v 1.46.0 --skip-dependencies

# Phase 2 — once per clone, at the repository root (ADR 0001).
astro dev init --runtime-version 3.3-7 --force
astro dev start --no-browser --wait 5m
```

`--runtime-version 3.3-7` is the exact pin ADR 0004 requires. `--force` is
needed because the repository root already holds committed files. Without it
`astro dev init` stops and asks:

```
C:\Projects\airflow-course is not an empty directory. Are you sure you want to
initialize a project here? (y/n)
```

Answering `y` is equivalent to `--force`. Nothing has to be moved out of the
way to make room for the Astro project.

`astro dev start` in Docker mode is not a foreground command — it returns once
the webserver reports healthy, bounded by `--wait`. It will not hang a session.

The resulting stack is **six** containers, not the five the generated
`README.md` claims: `postgres`, `db-migration` (one-shot, runs then exits),
`scheduler`, `dag-processor`, `api-server`, `triggerer`.

```
➤ Airflow UI: http://localhost:8080
➤ Postgres Database: postgresql://localhost:5432/postgres
```

`astro dev parse` is the cheapest proof the project is sound, and it exits
non-zero on a DAG import error. That is test seam 1.

## 2. The container engine is Docker, not Podman

This is a check, not an observation. Run all three; each is a positive signal
that cannot be produced by a Podman-backed run.

```sh
# (a) which Docker context the CLI would talk to
docker context ls
#   desktop-linux *   Docker Desktop   npipe:////./pipe/dockerDesktopLinuxEngine

# (b) the engine and the resources the containers actually get
docker info --format 'Name={{.Name}} Driver={{.Driver}} NCPU={{.NCPU}} MemTotal={{.MemTotal}}'
#   Name=docker-desktop Driver=overlayfs NCPU=16 MemTotal=8008667136

# (c) Astro stamps its own Docker-mode marker on every container it starts
docker ps --filter "label=com.docker.compose.project=airflow-course_d896a3" \
  --format '{{.Names}}' |
  while read n; do
    printf '%s io.astronomer.docker.cli=%s\n' "$n" \
      "$(docker inspect "$n" --format '{{index .Config.Labels "io.astronomer.docker.cli"}}')"
  done
#   airflow-course_d896a3-api-server-1 io.astronomer.docker.cli=true
#   airflow-course_d896a3-triggerer-1 io.astronomer.docker.cli=true
#   airflow-course_d896a3-dag-processor-1 io.astronomer.docker.cli=true
#   airflow-course_d896a3-scheduler-1 io.astronomer.docker.cli=true
#   airflow-course_d896a3-postgres-1 io.astronomer.docker.cli=true
```

(c) is the load-bearing one: `io.astronomer.docker.cli=true` is set by the Astro
CLI's Docker code path, so it cannot appear on a Podman run.

There is a fourth signal, available only during `astro dev start --verbosity
debug`, and it is the most direct — BuildKit names the builder instance it used:

```
#0 building with "desktop-linux" instance using docker driver
#4  [1/8] FROM astrocrpublic.azurecr.io/runtime:3.3-7@sha256:927684ace161d570e1e1fcd9a7c3d2cc99dfaefbc1ada2e566eca2b4dbca5708
```

**Caveat, and it matters here.** `podman` *is* present on this machine —
`C:\Users\ThalesCosta\AppData\Local\Programs\Podman\podman.exe`, Podman CLI
6.1.3 — installed before the course work began, not by the `--skip-dependencies`
install, which reported `Dependencies skipped.` So "Podman is not installed" is
**not** a valid check on this box. Only the positive signals above are.

## 3. What the container reports about itself

Read off the running container, never off a docs page:

```sh
docker exec airflow-course_d896a3-api-server-1 airflow version
#   3.3.1+astro.4
```

Corroborated from the image labels, which is a second independent read:

```
io.astronomer.docker.runtime.version = 3.3-7
io.astronomer.docker.airflow.version = 3.3.1+astro.4
io.astronomer.docker.airflow-task-sdk.version = 1.3.1+astro.2
io.astronomer.docker.python.version = 3.14
```

## 4. Hardware floor — this is inference, not a published minimum

> **Inference.** Astronomer publishes no minimum RAM or CPU figure for
> `astro dev`. Everything below is measured on this machine and generalised by
> judgement. Do not quote it as a vendor minimum.

| Quantity | Value | How measured |
| --- | --- | --- |
| Host physical RAM | 16,540,614,656 B (15.41 GiB) | `Win32_ComputerSystem.TotalPhysicalMemory` |
| RAM the containers may use | 8,008,667,136 B (7.46 GiB) | `docker info` `MemTotal` — the WSL2 VM, not the host |
| CPUs | 16 logical | `docker info` `NCPU` |
| Idle footprint, 5 running containers | ~1,029 MiB | `docker stats --no-stream` |
| Peak footprint during a real DAG run | ~1,470 MiB (1.44 GiB) | 100× 1 s samples of `docker stats` while `astro dev run dags test example_astronauts` ran |
| Peak per container under load | api-server 508 MiB, scheduler 414 MiB, triggerer 286 MiB, dag-processor 210 MiB, postgres 51 MiB | same samples |
| Local image size | 1.9 GB | `docker images` |

Two things this settles, both of which contradict the working assumption in
`RESOURCES.md` → Gaps:

1. The inference recorded there is "**≥8 GB for the 4-container footprint**".
   The footprint is five running containers plus a one-shot sixth, and it does
   not need 8 GB — the stack ran to completion in **7.46 GiB of ceiling with
   ~1.4 GiB actually used**, about a fifth of what was available. A working
   floor inferred from these numbers is nearer **2 GB allocated**, with CPU not
   a binding constraint at all (peak observed was under 2% of one core per
   container, on a 16-core box).
2. That run also had to fit *under* the 8 GB the earlier inference assumed —
   Docker Desktop capped the VM at 7.46 GiB, below the assumed bar, and
   nothing broke. The earlier figure was conservative by roughly an order of
   magnitude, not tight.

The honest floor therefore is stated as an inference and re-tested whenever the
container count grows, because a DAG that fans out over a large dynamic task
mapping is what will actually move these numbers.

## 5. The version gap, recorded as course content

| | Version | Source |
| --- | --- | --- |
| What the container runs | **3.3.1+astro.4** | `airflow version` inside the container, §3 |
| What the documentation describes | **3.3.2** | `RESOURCES.md` → *Airflow documentation (stable)*; confirmed against the docs' own version selector, which reads `Version: 3.3.2` |
| Astro Runtime supplying it | **3.3-7** | `Dockerfile` at the repository root; digest confirmed at build time in §2 |

The gap is real and it is **deliberate**. ADR 0003 names it as a consequence
accepted rather than hidden, and ADR 0004 pins the image to `3.3-7` on purpose
even though a newer Airflow patch exists. A learner who reads the stable docs
and then reads their own container sees two different version numbers on the
same day. That is the lesson, not a defect to smooth over: the CLI's release
cadence trails the ASF patch line, and the local runtime is chosen for a tested
composition (its bundled Task SDK, its provider set) rather than for the newest
patch number.

A second-order consequence worth teaching: because the local runtime is
`3.3.1+astro.4` and not `3.3.2`, the open question in `RESOURCES.md` → Gaps
about Cosmos `>=1.15.1,<1.16` on Airflow 3.3.2 **does not arise locally**. It
stays open, and it is only answered by an explicit Runtime upgrade — which
ADR 0004 makes its own lesson.

## 6. Why the compose configuration is a capture, not a file

ADR 0003 concedes that `astro dev start` "hides the deployment shape". It hides
it more completely than expected: the CLI builds its compose model in memory and
**never writes a compose file to disk**. Two independent observations:

```sh
# (a) the containers record no config file at all
docker inspect airflow-course_d896a3-postgres-1 \
  --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}'
#   (empty)

# (b) watching TEMP and the project root for a new *.yml / *.yaml across a full
#     `astro dev start` finds nothing — even at --verbosity debug
```

So the effective compose configuration is recovered from the running containers
instead and committed here:

- `reference/generated-compose.json` — the resolved shape: six services, image,
  command, entrypoint, environment, ports, mounts, depends-on, restart policy,
  and the Astro image labels.
- `reference/capture-compose.py` — the script that produced it, kept so the
  capture is repeatable rather than hand-copied.

Regenerate with the stack up:

```sh
python reference/capture-compose.py > reference/generated-compose.json
```

The `Dockerfile` needs no such treatment — `astro dev init` writes it, it is
committed, and it is one line: `FROM astrocrpublic.azurecr.io/runtime:3.3-7`.
