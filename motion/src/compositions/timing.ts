/**
 * The clip's timeline, in one place.
 *
 * Motion is used here for the thing ADR 0002 says it is for: the Airflow 3
 * component hand-off, where a single task's state has to change in a fixed
 * order across four processes. That ordering is hard to hold in prose and
 * trivial to watch, so it is a clip.
 *
 * Times are written in seconds and converted to frames with the composition's
 * fps, so re-timing the clip never means hand-editing frame numbers.
 */
export const HANDOFF_FPS = 30;

export const HANDOFF_DURATION_IN_FRAMES = 450; // 15.0s

export const beat = (seconds: number) => Math.round(seconds * HANDOFF_FPS);

/** Title settles. */
export const TITLE_IN = beat(0.2);
/** The DAG file is on disk. */
export const FILE_IN = beat(1.0);
/** The DAG processor parses it and writes the serialized DAG. */
export const PARSE_IN = beat(2.6);
/** The scheduler creates the TaskInstance: state becomes `queued`. */
export const QUEUE_IN = beat(5.0);
/** Dependencies satisfied, a worker slot free: state becomes `scheduled`. */
export const SCHEDULE_IN = beat(7.0);
/** A worker is executing the task. */
export const RUN_IN = beat(9.0);
/** The task returned; the state is written back. */
export const SUCCEED_IN = beat(12.0);
/** The full state ribbon is worth showing on its own. */
export const RIBBON_IN = beat(12.6);
