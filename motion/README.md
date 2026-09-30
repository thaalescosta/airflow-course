# Motion

Remotion projects for the course. One clip so far: `AirflowHandoff`.

## Remotion is authoring-time only

Nothing here is a runtime dependency of the course. A reader who opens a lesson
needs a browser and nothing else — no Node, no `npm install`, no render step. The
lesson embeds a committed MP4 from `clips/`, and that file is the artifact.

Editing a clip means running the toolchain **once, on the machine of whoever
authored it**, and committing the result. That is the whole contract, and it is
why this directory is a self-contained project rather than a `package.json` at
the repo root: the course's runtime has no business knowing Remotion exists.

## Layout

| Path | What it is | Committed? |
| --- | --- | --- |
| `src/Root.tsx` | The clip registry. The only place a composition is declared. | yes |
| `src/compositions/` | Composition sources. | yes |
| `src/lib/palette.ts` | House colours, matching the Tufte-style lessons. | yes |
| `remotion.config.ts` | Render-affecting config. Hashed by the seam, see below. | yes |
| `clips/*.mp4` | Rendered output. **Committed, never gitignored.** | yes |
| `clips/manifest.json` | Freshness manifest. Generated, never hand-edited. | yes |
| `scripts/render.mjs` | Renders every declared composition, writes the manifest. | yes |
| `scripts/check-freshness.mjs` | The media freshness seam. Zero dependencies. | yes |
| `node_modules/` | Installed toolchain. | no |

## Commands

```bash
npm install        # once, on the authoring machine
npm run studio     # preview a composition while editing it
npm run render     # render every declared composition into clips/, write the manifest
npm run check      # the learner-facing check: typecheck, then media freshness
```

The single command a learner runs to check the media is current is:

```bash
cd motion && npm run check
```

## The media freshness seam

`clips/manifest.json` records, for each committed clip, the sha256 of every
source file the render consumed, the sha256 and byte length of the rendered
file, and the Remotion version that produced it. `scripts/check-freshness.mjs`
re-derives all of that from what is on disk and exits non-zero on any
disagreement. It fails on three conditions:

1. **Source drift** — a source file that fed the render has changed since. This
   is the case the seam exists for: the composition moved, the clip did not.
2. **Output drift** — the committed file is missing, truncated, or has the right
   length but different bytes (re-encoded, re-muxed, hand-swapped).
3. **Undeclared media** — a file in `clips/` that no composition accounts for.

`remotion.config.ts` and `scripts/render.mjs` are in the hashed source set, because
between them they carry the codec, CRF, colour space and muting. Changing how the
pixels are *made* invalidates the committed clips too, rather than letting them
drift from the toolchain that is supposed to have produced them. The cost is that
editing even a comment in either file fails the check until the next render.

Two things are deliberately *not* checked:

- **Whether the animation teaches anything.** Pedagogical effectiveness is not
  automatable, and a test that claims to measure it measures nothing. That is a
  human judgement made by reading the lesson, not a green tick.
- **Whether the pixels decode.** That is asserted once, at render time, by
  `scripts/render.mjs`, which decodes the finished file and checks its duration
  and dimensions against the composition. The freshness check itself is
  dependency-free Node and never loads a video — it only hashes bytes.

## Adding a clip

1. Declare it in `src/Root.tsx` with its own `durationInFrames`, `fps` and
   dimensions.
2. Put the source in `src/compositions/`.
3. `npm run render`. This renders every declared composition — there is no
   per-clip flag — and rewrites the manifest.
4. `npm run check`.
5. Commit `src/`, `clips/*.mp4` and `clips/manifest.json` together.

Motion is used only where it is the only way to show the thing (ADR 0002):
dependency resolution, task-state transitions, the scheduler hand-off, task
fan-out. Anything that reads better as text in a lesson is not a clip.

## Pinning

Every dependency in `package.json` is pinned to an exact version, per ADR 0004.
Remotion's own packages must stay on the same exact version — they are released
in lockstep and a mismatch between `remotion` and `@remotion/renderer` fails at
render time rather than at install time.
