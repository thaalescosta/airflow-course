import React from 'react';
import {
  AbsoluteFill,
  Easing,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {mono, palette, sans} from '../lib/palette';
import {
  FILE_IN,
  PARSE_IN,
  QUEUE_IN,
  RIBBON_IN,
  RUN_IN,
  SCHEDULE_IN,
  SUCCEED_IN,
  TITLE_IN,
} from './timing';

const CARD_TOP = 306;
const CARD_HEIGHT = 228;
const CARD_WIDTH = 392;
const CARD_GAP = 56;
const CARD_LEFT = 92;

const STAGES = [
  {
    at: FILE_IN,
    title: 'DAG file',
    body: 'dags/pipeline/\ndaily_orders.py',
    isCode: true,
  },
  {
    at: PARSE_IN,
    title: 'DAG processor',
    body: 'Parses it.\nNever runs task code.',
    isCode: false,
  },
  {
    at: QUEUE_IN,
    title: 'Scheduler',
    body: 'Writes one row\nper task.',
    isCode: false,
  },
  {
    at: RUN_IN,
    title: 'Worker',
    body: 'Runs the task,\nwrites state back.',
    isCode: false,
  },
] as const;

const STATE_STEPS = [
  {label: 'queued', at: QUEUE_IN, color: palette.blue, soft: palette.blueSoft},
  {label: 'scheduled', at: SCHEDULE_IN, color: palette.amber, soft: palette.amberSoft},
  {label: 'running', at: RUN_IN, color: palette.blue, soft: palette.blueSoft},
  {label: 'success', at: SUCCEED_IN, color: palette.green, soft: palette.greenSoft},
] as const;

const RIBBON_STATES = ['none', 'queued', 'scheduled', 'running', 'success'] as const;

const ENTER = {damping: 200, mass: 0.6, stiffness: 140};

const Arrow: React.FC<{x: number; y: number; at: number}> = ({x, y, at}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  return (
    <div
      style={{
        position: 'absolute',
        left: x,
        top: y,
        width: CARD_GAP,
        height: 3,
        backgroundColor: palette.rule,
      }}
    >
      <div
        style={{
          position: 'absolute',
          inset: 0,
          backgroundColor: palette.ink,
          transformOrigin: 'left center',
          scale: `${interpolate(frame, [at, at + 0.35 * fps], [0, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
            easing: Easing.bezier(0.16, 1, 0.3, 1),
          })} 1`,
        }}
      />
      <div
        style={{
          position: 'absolute',
          right: -2,
          top: -7,
          borderLeft: `14px solid ${palette.ink}`,
          borderTop: '9px solid transparent',
          borderBottom: '9px solid transparent',
          opacity: interpolate(frame, [at + 0.3 * fps, at + 0.5 * fps], [0, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          }),
        }}
      />
    </div>
  );
};

const Card: React.FC<{
  x: number;
  index: number;
  title: string;
  body: string;
  isCode: boolean;
  at: number;
}> = ({x, index, title, body, isCode, at}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  return (
    <div
      style={{
        position: 'absolute',
        left: x,
        top: CARD_TOP,
        width: CARD_WIDTH,
        height: CARD_HEIGHT,
        boxSizing: 'border-box',
        padding: '30px 28px',
        backgroundColor: palette.card,
        border: `2px solid ${palette.rule}`,
        borderTop: `6px solid ${index === 0 ? palette.ink : palette.blue}`,
        opacity: interpolate(frame, [at, at + 0.4 * fps], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        }),
        translate: `0 ${interpolate(spring({frame: frame - at, fps, config: ENTER}), [0, 1], [
          36,
          0,
        ])}px`,
      }}
    >
      <div
        style={{
          fontFamily: sans,
          fontSize: 44,
          fontWeight: 600,
          color: palette.ink,
          lineHeight: 1.1,
        }}
      >
        {title}
      </div>
      <div
        style={{
          marginTop: 18,
          fontFamily: isCode ? mono : sans,
          fontSize: isCode ? 27 : 30,
          color: palette.muted,
          lineHeight: 1.42,
          whiteSpace: 'pre-line',
        }}
      >
        {body}
      </div>
    </div>
  );
};

const StatePanel: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const step =
    [...STATE_STEPS].reverse().find((candidate) => frame >= candidate.at) ?? null;

  const live = step !== null && step.label === 'running';

  return (
    <div
      style={{
        position: 'absolute',
        left: CARD_LEFT,
        top: 666,
        width: CARD_LEFT * 2 + CARD_WIDTH * 4 + CARD_GAP * 3,
        height: 164,
        boxSizing: 'border-box',
        padding: '26px 32px',
        display: 'flex',
        alignItems: 'center',
        gap: 40,
        backgroundColor: palette.card,
        border: `2px solid ${palette.rule}`,
        opacity: interpolate(frame, [QUEUE_IN - 0.4 * fps, QUEUE_IN + 0.2 * fps], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        }),
      }}
    >
      <div
        style={{
          width: 380,
          flexShrink: 0,
          fontFamily: mono,
          lineHeight: 1.35,
        }}
      >
        <div style={{fontSize: 26, color: palette.muted}}>TaskInstance</div>
        <div style={{fontSize: 32, color: palette.ink, marginTop: 8}}>orders / extract</div>
      </div>
      <div
        style={{
          width: 340,
          height: 74,
          flexShrink: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxSizing: 'border-box',
          borderRadius: 8,
          backgroundColor: step ? step.soft : palette.paper,
          border: `2px solid ${step ? step.color : palette.rule}`,
          color: step ? step.color : palette.muted,
          fontFamily: mono,
          fontSize: 32,
          letterSpacing: 1,
          opacity: live
            ? 0.72 + 0.28 * Math.abs(Math.sin((frame / fps) * Math.PI * 1.6))
            : 1,
        }}
      >
        {step ? step.label : 'not created'}
      </div>
      <div
        style={{
          flex: 1,
          fontFamily: sans,
          fontSize: 30,
          color: palette.muted,
          lineHeight: 1.42,
        }}
      >
        <span style={{color: palette.ink, fontWeight: 600}}>API server</span> reads that same
        row. The grid you watch is a read of this state, not a view of a running process.
      </div>
    </div>
  );
};

const Ribbon: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const width = CARD_LEFT * 2 + CARD_WIDTH * 4 + CARD_GAP * 3;
  const stepWidth = (width - 40) / (RIBBON_STATES.length - 1);
  const active =
    frame < QUEUE_IN
      ? 0
      : frame < SCHEDULE_IN
        ? 1
        : frame < RUN_IN
          ? 2
          : frame < SUCCEED_IN
            ? 3
            : 4;

  return (
    <div
      style={{
        position: 'absolute',
        left: CARD_LEFT,
        top: 878,
        width,
        opacity: interpolate(frame, [RIBBON_IN, RIBBON_IN + 0.4 * fps], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        }),
      }}
    >
      <div
        style={{
          position: 'absolute',
          left: 20,
          right: 20,
          top: 15,
          height: 2,
          backgroundColor: palette.rule,
        }}
      />
      {RIBBON_STATES.map((label, index) => {
        const reached = index <= active && index > 0;
        const isCurrent = index === active && index > 0;

        return (
          <div
            key={label}
            style={{
              position: 'absolute',
              left: 20 + index * stepWidth,
              top: 0,
              width: 0,
              display: 'flex',
              flexDirection: 'column',
              alignItems: index === 0 ? 'flex-start' : index === RIBBON_STATES.length - 1 ? 'flex-end' : 'center',
            }}
          >
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: 16,
                boxSizing: 'border-box',
                border: `3px solid ${reached ? palette.ink : palette.rule}`,
                backgroundColor: isCurrent ? palette.ink : palette.paper,
                scale: isCurrent
                  ? `${interpolate(spring({frame: frame - RIBBON_IN, fps, config: ENTER}), [0, 1], [0.7, 1])}`
                  : '1',
              }}
            />
            <div
              style={{
                marginTop: 14,
                fontFamily: mono,
                fontSize: 30,
                whiteSpace: 'nowrap',
                color: isCurrent ? palette.ink : reached ? palette.muted : palette.rule,
                fontWeight: isCurrent ? 700 : 400,
              }}
            >
              {label}
            </div>
          </div>
        );
      })}
    </div>
  );
};

export const AirflowHandoff: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const writtenToStore = frame >= PARSE_IN + 0.5 * fps;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: palette.paper,
        fontFamily: sans,
        color: palette.ink,
      }}
    >
      <div
        style={{
          position: 'absolute',
          left: CARD_LEFT,
          top: 104,
          fontSize: 84,
          fontWeight: 600,
          letterSpacing: -1.5,
          opacity: interpolate(frame, [TITLE_IN, TITLE_IN + 0.5 * fps], [0, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          }),
          translate: `0 ${interpolate(spring({frame: frame - TITLE_IN, fps, config: ENTER}), [0, 1], [24, 0])}px`,
        }}
      >
        One task, four processes
      </div>
      <div
        style={{
          position: 'absolute',
          left: CARD_LEFT,
          top: 212,
          fontSize: 40,
          color: palette.muted,
          opacity: interpolate(frame, [TITLE_IN + 0.2 * fps, TITLE_IN + 0.8 * fps], [0, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          }),
        }}
      >
        What actually happens between the Python file and the green square.
      </div>

      {STAGES.map((stage, index) => {
        const x = CARD_LEFT + index * (CARD_WIDTH + CARD_GAP);

        return (
          <React.Fragment key={stage.title}>
            <Card
              x={x}
              index={index}
              title={stage.title}
              body={stage.body}
              isCode={stage.isCode}
              at={stage.at}
            />
            {index < STAGES.length - 1 ? (
              <Arrow
                x={x + CARD_WIDTH}
                y={CARD_TOP + CARD_HEIGHT / 2 - 1}
                at={STAGES[index + 1].at - 0.5 * fps}
              />
            ) : null}
          </React.Fragment>
        );
      })}

      <div
        style={{
          position: 'absolute',
          left: CARD_LEFT,
          top: 566,
          width: CARD_LEFT * 2 + CARD_WIDTH * 4 + CARD_GAP * 3,
          height: 72,
          boxSizing: 'border-box',
          padding: '0 30px',
          display: 'flex',
          alignItems: 'center',
          gap: 22,
          border: `2px dashed ${palette.rule}`,
          backgroundColor: palette.blueSoft,
          opacity: interpolate(frame, [PARSE_IN + 0.3 * fps, PARSE_IN + 0.7 * fps], [0, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          }),
        }}
      >
        <div style={{fontSize: 32, fontWeight: 700, color: palette.blue, flexShrink: 0}}>
          Metadata DB
        </div>
        <div style={{fontSize: 28, color: palette.muted, flex: 1, lineHeight: 1.35}}>
          Serialized DAGs and TaskInstance state. Task code never touches this.
        </div>
        <div
          style={{
            flexShrink: 0,
            fontFamily: mono,
            fontSize: 26,
            whiteSpace: 'nowrap',
            color: writtenToStore ? palette.blue : palette.muted,
          }}
        >
          {writtenToStore ? 'serializedDag written' : 'idle'}
        </div>
      </div>

      <StatePanel />
      <Ribbon />
    </AbsoluteFill>
  );
};
