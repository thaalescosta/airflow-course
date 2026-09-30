# AGENTS.md

## Authoring convention (filename decision)

The authoring and project convention file is named `AGENTS.md`. This choice follows the vendor-neutral convention that works across agent tools (Codex, opencode, Claude Code, and others). The decision was established as part of agent-skill setup; the reasoning is recorded here in the same declarative style as the settled ADRs. The repository's full authoring rules belong in this file (agent-facing convention) rather than as an additional ADR, because the seven ADRs enumerate settled architecture decisions and are not to be re-litigated.

## Repository layout and naming

Single-context: one `GLOSSARY.md` and one `docs/adr/` at the repo root.

- Repo root is the Astro CLI project (ADR 0001). `dags/`, `Dockerfile`, `requirements.txt`, `.astro/`, `include/`, `plugins/` live at top level alongside `lessons/`, `reference/`, `assets/`, `learning-records/`, `motion/`.
- `lessons/`: self-contained HTML lesson documents (Tufte-style), spine for content (ADR 0002).
- `assets/`: shared stylesheets and static assets for lessons.
- `reference/`: long-lived reference material that persists across lessons.
- `learning-records/`: per-lesson records produced by the learner/agent when practicing; populated during lesson execution.
- `motion/`: Remotion projects/clips used only when motion is the only way to show a concept (ADR 0002).
- `dags/` namespaced: `dags/pipeline/` is the continuous project; `dags/exercises/` holds per-lesson throwaway DAGs; `dags/dbt/` holds the dbt project Cosmos expects (ADR 0001).
- dbt project: `dags/dbt/` (ADR 0001), taught standalone before Cosmos (ADR 0006). Models follow dbt best practices (stg→int→fct/marts as appropriate).
- DAG namespaces: use clear, stable module paths aligned with the above namespaces (`pipeline.*`, `exercises.*`). DAG IDs are explicit, snake_case, and stable across lesson progression.

## Lesson anatomy (required)

Every lesson must contain:

1. **The specification-shaped exercise** — a requirement, the relevant API surface, and the constraints; exercises are specifications, not code to copy (ADR 0007). Give the task as a concrete spec (inputs/outputs, boundaries).
2. **The worked example placed away from the exercise** — a concrete implementation/example located in a separate, clearly referenced location from the exercise text (not co-located so it cannot be mechanically transcribed).
3. **The statement of what was just built** — a concise declarative statement that says what was built/achieved by completing the exercise (the artifact/result).
4. **The primary source cited** — at least one citation to an entry in `RESOURCES.md` (the source-of-truth policy); knowledge traces back to `RESOURCES.md`.
5. **The primary source recommended next** — the next recommended primary source from `RESOURCES.md` (or a specific anchor) to continue.
6. **The follow-up-question prompt** — a concrete, answerable follow-up question that forces synthesis/application (not a yes/no triviality).

## Glossary policy

No course-wide glossary is generated up front. A term is promoted into `GLOSSARY.md` only when it has been demonstrated correct use in context (per domain rules: "add a term only when the user understands it"). Populate incrementally as concepts are actually internalized.

## Test seams (four)

The four test seams are:
1. **DAG parsing/validation** — structural checks (e.g. `astro dev parse`, or DAG import/validation); catches syntax and import-time errors.
2. **Unit/integration seams at task boundaries** — test task logic in isolation (separating pure logic from Airflow runtime where possible).
3. **Pipeline assertions/integration runs** — end-to-end or incremental pipeline behavior (state, data correctness, backfills/idempotency).
4. **dbt tests** — schema/data tests for dbt models (unique/not_null/relationships/custom), run standalone and via Cosmos.

The **primary test seam** is **pipeline assertions (seam 3)** because the course is a continuous project and correctness is demonstrated by pipeline behavior across re-runs and backfills. Other seams support it.

## Settled ADRs (not to be re-litigated)

The following seven ADRs in `docs/adr/` are settled and not up for re-litigation without cause:
- 0001-repo-root-is-the-astro-project.md
- 0002-html-lessons-spine-remotion-for-motion.md
- 0003-astro-cli-over-vanilla-compose.md
- 0004-pin-every-dependency-exactly.md
- 0005-synthetic-api-as-data-source.md
- 0006-dbt-standalone-before-cosmos.md
- 0007-exercises-are-specifications.md

See `docs/agents/domain.md` for consumer rules.

## Agent skills

### Issue tracker

Issues and specs live as GitHub issues in this repo, created and read with the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical roles: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and one `docs/adr/` at the repo root. See `docs/agents/domain.md`.
