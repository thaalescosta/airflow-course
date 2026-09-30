# Domain docs

## Layout

Single-context. One `GLOSSARY.md` at the repo root, one `docs/adr/` at the repo root.

## Consumer rules

- Read `MISSION.md` before teaching anything. Every lesson traces back to it.
- Read `RESOURCES.md` before asserting any fact about Airflow, dbt, or Astronomer tooling. Never trust parametric memory on version numbers, CLI flags, or API surfaces — the ground moves faster than training data. Every lesson cites a source from this file.
- Read `docs/adr/` before changing structure. Seven decisions are already recorded and are not up for re-litigation without cause: the repo root is the Astro project; HTML is the artifact spine and Remotion is only for motion; Astro CLI over hand-written compose; exact dependency pins with upgrades taught; a synthetic frozen API as the data source; standalone dbt before Cosmos; exercises are specifications.
- `GLOSSARY.md` does not exist yet, by design. It is populated only with terms the learner has demonstrated correct use of — per the `teach` rule, "add a term only when the user understands it."
