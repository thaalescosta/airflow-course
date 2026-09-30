import {Config} from '@remotion/cli/config';

// This file is part of the media freshness seam: `scripts/check-freshness.mjs`
// hashes it together with `src/`, so a render-affecting change here invalidates
// every committed clip instead of silently drifting from it.
//
// Anything set here is the Studio/CLI default. `scripts/render.mjs` drives
// @remotion/renderer directly and passes the equivalent options explicitly, so
// keep the two in step.

Config.setVideoImageFormat('jpeg');
Config.setCodec('h264');
Config.setCrf(18);
Config.setOverwriteOutput(true);
Config.setChromiumDisableWebSecurity(false);
Config.setMuted(true);
