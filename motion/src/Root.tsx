import React from 'react';
import {Composition} from 'remotion';
import {AirflowHandoff} from './compositions/AirflowHandoff';
import {HANDOFF_DURATION_IN_FRAMES, HANDOFF_FPS} from './compositions/timing';

/**
 * The clip registry. This file is the only place a composition is declared.
 *
 * `scripts/render.mjs` asks the bundle what compositions exist
 * (`getCompositions()`), renders each into `clips/`, and records the outcome in
 * `clips/manifest.json`. `scripts/check-freshness.mjs` re-derives that manifest
 * from the current sources and fails if the committed media and these
 * declarations disagree. Declaring a composition without rendering it, or
 * editing one without re-rendering, is exactly the drift the seam exists to
 * catch.
 */
export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="AirflowHandoff"
        component={AirflowHandoff}
        durationInFrames={HANDOFF_DURATION_IN_FRAMES}
        fps={HANDOFF_FPS}
        width={1920}
        height={1080}
      />
    </>
  );
};
