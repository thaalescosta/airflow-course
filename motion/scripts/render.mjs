/**
 * Renders every composition declared in `src/Root.tsx` into `clips/`, then
 * writes `clips/manifest.json`.
 *
 * The manifest is the entire mechanism behind the media freshness seam. It
 * records, per committed clip:
 *
 *   - the sha256 of every source file the composition was built from, so an
 *     edit to any of them is detectable without re-rendering anything;
 *   - the sha256 and byte length of the rendered file, so a re-encoded,
 *     truncated or hand-swapped clip is detectable too;
 *   - the Remotion version that produced it, reported (not enforced) by the
 *     freshness check.
 *
 * Nothing else in the course notices when a clip drifts from its composition,
 * which is the whole reason this file exists.
 *
 * Run with: npm run render
 */
import {bundle} from '@remotion/bundler';
import {
  getCompositions,
  getVideoMetadata,
  renderMedia,
  selectComposition,
} from '@remotion/renderer';
import {createHash} from 'node:crypto';
import {readdir, readFile, stat, writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const PROJECT_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const ENTRY_POINT = path.join(PROJECT_ROOT, 'src', 'index.ts');
const CLIPS_DIR = path.join(PROJECT_ROOT, 'clips');
const MANIFEST_PATH = path.join(CLIPS_DIR, 'manifest.json');
const BUNDLE_DIR = path.join(PROJECT_ROOT, 'node_modules', '.remotion', 'bundle');

/** Extensions that can change what a composition renders. */
const SOURCE_EXTENSIONS = new Set(['.ts', '.tsx']);
/**
 * Beyond `src/`, these can change how a render is produced: the CLI config and
 * this script, which between them carry the codec, CRF, colour space and
 * muting. They are hashed alongside the composition sources so that changing
 * how the pixels are made invalidates the committed clips, instead of letting
 * them drift from the toolchain that is supposed to have produced them.
 *
 * The cost of including them is that editing even a comment here fails the
 * freshness check until the next render. That is the intended direction to err.
 */
const EXTRA_SOURCES = ['remotion.config.ts', 'scripts/render.mjs'];

const sha256 = (buffer) => createHash('sha256').update(buffer).digest('hex');

const toPosix = (value) => value.split(path.sep).join('/');

const kebab = (value) =>
  value
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .replace(/[^a-zA-Z0-9]+/g, '-')
    .toLowerCase();

const collectSources = async (directory, prefix) => {
  const entries = await readdir(directory, {withFileTypes: true});
  const found = [];

  for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
    if (entry.isDirectory()) {
      found.push(...(await collectSources(path.join(directory, entry.name), `${prefix}${entry.name}/`)));
      continue;
    }

    if (SOURCE_EXTENSIONS.has(path.extname(entry.name))) {
      found.push(prefix + entry.name);
    }
  }

  return found;
};

const readPackage = async () => {
  const raw = await readFile(path.join(PROJECT_ROOT, 'package.json'), 'utf8');
  return JSON.parse(raw);
};

const hashSources = async (relativePaths) => {
  const sources = [];

  for (const relativePath of relativePaths) {
    const buffer = await readFile(path.join(PROJECT_ROOT, relativePath));
    sources.push({path: toPosix(relativePath), sha256: sha256(buffer)});
  }

  return sources;
};

const main = async () => {
  const pkg = await readPackage();
  const remotionVersion = pkg.dependencies.remotion;
  const sourcePaths = [...(await collectSources(path.join(PROJECT_ROOT, 'src'), 'src/')), ...EXTRA_SOURCES];

  for (const relativePath of sourcePaths) {
    await stat(path.join(PROJECT_ROOT, relativePath));
  }

  // Hash before rendering: the manifest must describe the tree that produced
  // the pixels, not a tree edited while the render was in flight.
  const sources = await hashSources(sourcePaths);

  process.stdout.write(`bundling ${toPosix(path.relative(PROJECT_ROOT, ENTRY_POINT))}\n`);
  const serveUrl = await bundle({entryPoint: ENTRY_POINT, outDir: BUNDLE_DIR});

  const compositions = await getCompositions(serveUrl, {
    logLevel: 'error',
  });

  if (compositions.length === 0) {
    throw new Error('No compositions declared in src/Root.tsx — nothing to render.');
  }

  const clips = [];

  for (const summary of compositions) {
    const fileName = `${kebab(summary.id)}.mp4`;
    const outputLocation = path.join(CLIPS_DIR, fileName);

    const composition = await selectComposition({
      serveUrl,
      id: summary.id,
      logLevel: 'error',
    });

    process.stdout.write(
      `rendering ${summary.id}  ${composition.width}x${composition.height}  ` +
        `${composition.fps}fps  ${composition.durationInFrames} frames\n`,
    );

    await renderMedia({
      composition,
      serveUrl,
      codec: 'h264',
      crf: 18,
      imageFormat: 'jpeg',
      muted: true,
      overwrite: true,
      outputLocation,
      // Frames are captured as JPEG, which ffmpeg flags full-range; without an
      // explicit colour space tag the output comes out as the deprecated
      // yuvj420p and plays back with the wrong range. Tagging it keeps the
      // committed MP4 a plain, standard yuv420p.
      colorSpace: 'bt709',
      logLevel: 'error',
      onBrowserDownload: () => {
        process.stdout.write('downloading headless browser\n');
      },
    });

    // Decoding the finished file is the only proof that it is a real video
    // rather than a non-empty file. The freshness check cannot do this — it
    // runs without the render toolchain — so it is asserted here, once.
    const [output, metadata] = await Promise.all([
      stat(outputLocation),
      getVideoMetadata(outputLocation, {logLevel: 'error'}),
    ]);

    if (output.size === 0) {
      throw new Error(`${fileName} rendered to zero bytes.`);
    }

    const expectedSeconds = composition.durationInFrames / composition.fps;
    const actualSeconds = metadata.durationInSeconds;

    if (actualSeconds === null) {
      throw new Error(`${fileName} has no decodable duration.`);
    }

    if (Math.abs(actualSeconds - expectedSeconds) > 0.25) {
      throw new Error(
        `${fileName} decoded to ${actualSeconds.toFixed(3)}s, expected ${expectedSeconds.toFixed(3)}s.`,
      );
    }

    if (metadata.width !== composition.width || metadata.height !== composition.height) {
      throw new Error(
        `${fileName} decoded to ${metadata.width}x${metadata.height}, ` +
          `expected ${composition.width}x${composition.height}.`,
      );
    }

    if (!metadata.canPlayInVideoTag) {
      throw new Error(`${fileName} decoded to a codec a browser cannot play in a <video> tag.`);
    }

    process.stdout.write(
      `  wrote ${fileName}  ${output.size} B  decoded ${metadata.width}x${metadata.height} ` +
        `${actualSeconds.toFixed(2)}s ${metadata.codec} playable-in-video-tag\n`,
    );

    clips.push({
      compositionId: summary.id,
      file: fileName,
      composition: {
        width: composition.width,
        height: composition.height,
        fps: composition.fps,
        durationInFrames: composition.durationInFrames,
      },
      decoded: {
        width: metadata.width,
        height: metadata.height,
        durationInSeconds: Number(actualSeconds.toFixed(3)),
        codec: metadata.codec,
        canPlayInVideoTag: metadata.canPlayInVideoTag,
      },
      output: {
        bytes: output.size,
        sha256: sha256(await readFile(outputLocation)),
      },
      renderedWith: {remotion: remotionVersion},
      sources,
    });
  }

  clips.sort((a, b) => a.compositionId.localeCompare(b.compositionId));

  const manifest = {
    $comment:
      'Generated by scripts/render.mjs. Do not hand-edit. Verified by scripts/check-freshness.mjs, ' +
      'which is the media freshness seam: it re-hashes every source file and every clip and fails ' +
      'if either has moved since this manifest was written.',
    manifestVersion: 1,
    clips,
  };

  await writeFile(MANIFEST_PATH, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');
  process.stdout.write(`wrote ${toPosix(path.relative(PROJECT_ROOT, MANIFEST_PATH))}\n`);
};

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.stack : String(error)}\n`);
  process.exit(1);
});
