/**
 * House palette for course motion.
 *
 * Deliberately the same light "paper" register as the Tufte-style lessons in
 * `lessons/`, so a clip embedded in a lesson reads as part of the page rather
 * than as a screen recording dropped into it.
 */
export const palette = {
  paper: '#fbfbf7',
  card: '#ffffff',
  ink: '#14140f',
  muted: '#6c6c62',
  rule: '#dcdcd2',
  blue: '#14568f',
  blueSoft: '#e7eff7',
  green: '#1f7a4d',
  greenSoft: '#e6f2ec',
  amber: '#a05c00',
  amberSoft: '#fbf0e0',
  red: '#a32a1c',
} as const;

export const sans =
  '"Segoe UI", Inter, -apple-system, BlinkMacSystemFont, Roboto, Helvetica, Arial, sans-serif';

export const mono =
  'Cascadia Mono, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace';
