/**
 * The media freshness seam.
 *
 * A committed clip and the composition that produced it are two separate
 * artifacts that nothing in this course otherwise relates to one another. Edit
 * a composition, forget to re-render, and the lesson keeps serving the old
 * pixels — silently, until a learner watches the wrong thing. That is the only
 * thing this check exists to prevent.
 *
 * It compares two things, both against `clips/manifest.json` as written by
 * `scripts/render.mjs`:
 *
 *   1. Source drift. Every source file the render consumed is re-hashed. Any
 *      mismatch means the composition has moved and the clip is stale.
 *   2. Output integrity. Each committed clip is re-hashed and its byte length
 *      compared, so a truncated, re-encoded or swapped file is caught too.
 *
 * It also fails on media in `clips/` that the manifest does not declare, which
 * is the same drift in the other direction: a clip that no composition accounts
 * for.
 *
 * Deliberately NOT checked, because neither is automatable and a check that
 * measures nothing is worse than no check:
 *   - whether the animation is pedagogically effective;
 *   - whether the pixels decode. That is asserted once at render time by
 *     `scripts/render.mjs`, which is the only place the render toolchain runs.
 *
 * Zero dependencies: Node built-ins only, so this runs without installing
 * anything and without a browser.
 *
 * Run with: npm run check   (or npm run check:freshness)
 */
import {createHash} from 'node:crypto';
import {readdir, readFile, stat} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const PROJECT_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const CLIPS_DIR = path.join(PROJECT_ROOT, 'clips');
const MANIFEST_PATH = path.join(CLIPS_DIR, 'manifest.json');
const RENDER_COMMAND = 'cd motion && npm run render';

const MEDIA_EXTENSIONS = new Set(['.mp4', '.webm', '.mov', '.gif', '.mkv', '.m4v']);

const sha256 = (buffer) => createHash('sha256').update(buffer).digest('hex');

const shortHash = (value) => (typeof value === 'string' ? value.slice(0, 12) : '?');

const relative = (absolute) => path.relative(PROJECT_ROOT, absolute).split(path.sep).join('/');

const exists = async (target) => {
  try {
    await stat(target);
    return true;
  } catch {
    return false;
  }
};

const readManifest = async () => {
  if (!(await exists(MANIFEST_PATH))) {
    return {error: `clips/manifest.json is missing. No clip has ever been rendered here.`};
  }

  let manifest;

  try {
    manifest = JSON.parse(await readFile(MANIFEST_PATH, 'utf8'));
  } catch (error) {
    return {error: `clips/manifest.json is not valid JSON: ${error.message}`};
  }

  if (!Array.isArray(manifest.clips) || manifest.clips.length === 0) {
    return {error: 'clips/manifest.json declares no clips. Expected at least one committed clip.'};
  }

  return {manifest};
};

const checkClip = async (clip) => {
  const problems = [];
  const notes = [];

  const clipPath = path.join(CLIPS_DIR, clip.file);

  if (!(await exists(clipPath))) {
    problems.push(`${clip.file} is declared in the manifest but is not on disk.`);
  } else {
    const [output, buffer] = await Promise.all([stat(clipPath), readFile(clipPath)]);

    if (output.size !== clip.output.bytes) {
      problems.push(
        `${clip.file} is ${output.size} bytes, manifest recorded ${clip.output.bytes}. ` +
          'The file was replaced or truncated.',
      );
    } else if (sha256(buffer) !== clip.output.sha256) {
      problems.push(
        `${clip.file} has the same length as the manifest recorded but different bytes. ` +
          'The file was replaced or re-encoded.',
      );
    }
  }

  const sources = Array.isArray(clip.sources) ? clip.sources : [];
  const drifted = [];

  for (const source of sources) {
    const sourcePath = path.join(PROJECT_ROOT, source.path);

    if (!(await exists(sourcePath))) {
      drifted.push(`${source.path} (deleted)`);
      continue;
    }

    if (sha256(await readFile(sourcePath)) !== source.sha256) {
      drifted.push(source.path);
    }
  }

  if (drifted.length > 0) {
    problems.push(
      `the composition source changed after this clip was rendered: ${drifted.join(', ')}. ` +
        'The committed media is stale.',
    );
  }

  if (clip.renderedWith?.remotion) {
    notes.push(`rendered with remotion ${clip.renderedWith.remotion}`);
  }

  return {problems, notes, sourceCount: sources.length, unchanged: sources.length - drifted.length};
};

const findUndeclaredMedia = async (declared) => {
  const entries = await readdir(CLIPS_DIR, {withFileTypes: true});
  const known = new Set(declared);

  return entries
    .filter(
      (entry) =>
        entry.isFile() && MEDIA_EXTENSIONS.has(path.extname(entry.name).toLowerCase()),
    )
    .map((entry) => entry.name)
    .filter((name) => !known.has(name))
    .sort();
};

const main = async () => {
  const lines = [];
  const {manifest, error} = await readManifest();

  lines.push('media freshness  motion/clips');

  if (error) {
    lines.push('');
    lines.push(`FAIL  ${error}`);
    lines.push(`      Nothing is committed that any composition claims to have produced.`);
    lines.push(`      Fix:  ${RENDER_COMMAND}`);
    process.stdout.write(`${lines.join('\n')}\n`);
    process.exit(1);
  }

  let staleClips = 0;
  const undeclared = await findUndeclaredMedia(manifest.clips.map((clip) => clip.file));

  for (const clip of manifest.clips) {
    const result = await checkClip(clip);
    const failed = result.problems.length > 0;

    if (failed) {
      staleClips += 1;
    }

    lines.push('');
    lines.push(`  ${failed ? 'STALE' : ' ok  '}  ${clip.file}  <- ${clip.compositionId}`);
    lines.push(
      `          sources  ${result.unchanged}/${result.sourceCount} unchanged` +
        (result.sourceCount === 0 ? '  (manifest recorded no sources — re-render)' : ''),
    );
    lines.push(`          output   sha256 ${shortHash(clip.output.sha256)} recorded`);
    lines.push(`          render   ${result.notes.join(', ') || 'unknown'}`);

    for (const problem of result.problems) {
      lines.push(`          ! ${problem}`);
    }
  }

  const clipCount = manifest.clips.length;

  if (undeclared.length > 0) {
    lines.push('');
    for (const name of undeclared) {
      lines.push(`  STALE  ${name}  <- no composition declares this clip`);
      lines.push('          ! Media in clips/ that the manifest does not account for.');
    }
  }

  lines.push('');

  const failures = staleClips + undeclared.length;

  if (failures > 0) {
    const parts = [];
    if (staleClips > 0) {
      parts.push(`${staleClips} stale`);
    }
    if (undeclared.length > 0) {
      parts.push(`${undeclared.length} undeclared`);
    }

    lines.push(
      `FAIL  ${parts.join(', ')} of ${clipCount} committed clip(s); ` +
        'the media no longer matches the compositions that produced it.',
    );
    lines.push('      The lesson would be serving media that is not what the composition produces.');
    lines.push(`      Fix:  ${RENDER_COMMAND}   (then commit clips/ again)`);
    process.stdout.write(`${lines.join('\n')}\n`);
    process.exit(1);
  }

  lines.push(`PASS  ${clipCount} committed clip(s) match their composition source.`);
  process.stdout.write(`${lines.join('\n')}\n`);
};

main().catch((error) => {
  process.stderr.write(`media freshness: ${error instanceof Error ? error.stack : String(error)}\n`);
  process.exit(1);
});
