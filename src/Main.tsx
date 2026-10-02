import React from 'react';
import {AbsoluteFill, OffthreadVideo, Sequence, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {SceneView, SfxContext, SplitBackground} from './scenes';
import type {Plan, SplitScene} from './types';
import {FilmLook, resolveSrc} from './ui/kit';
import './ui/theme';

// All templates are laid out on a 1920x1080 canvas and scaled to the output size.
const W = 1920;
const H = 1080;
const SPLIT_EASE = 12;

/** The talking avatar. During `split` scenes it shrinks into a framed photo on one side. */
const Avatar: React.FC<{plan: Plan}> = ({plan}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const split = plan.scenes.find(
    (s): s is SplitScene => s.type === 'split' && frame >= s.start * fps && frame < s.end * fps,
  );
  let p = 0;
  let side = -1;
  if (split) {
    const a = split.start * fps;
    const b = split.end * fps;
    p = Math.min(
      interpolate(frame, [a, a + SPLIT_EASE], [0, 1], {extrapolateRight: 'clamp'}),
      interpolate(frame, [b - SPLIT_EASE, b], [1, 0], {extrapolateLeft: 'clamp'}),
    );
    p = 1 - Math.pow(1 - p, 3);
    side = (split.avatar ?? 'left') === 'left' ? -1 : 1;
  }
  const scale = 1 - 0.56 * p;
  const tx = side * 470 * p;
  return (
    <AbsoluteFill
      style={{
        transform: `translate(${tx}px, ${-10 * p}px) scale(${scale}) rotate(${side * 1.5 * p}deg)`,
        boxShadow: p > 0 ? `0 0 0 ${(22 * p) / scale}px #f3efe6, 0 30px 60px rgba(0,0,0,${0.6 * p})` : undefined,
      }}
    >
      <OffthreadVideo src={resolveSrc(plan.video)} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
    </AbsoluteFill>
  );
};

export const Main: React.FC<Plan> = (plan) => {
  const {width, fps} = useVideoConfig();
  const seq = (start: number, end: number) => ({
    from: Math.round(start * fps),
    durationInFrames: Math.max(1, Math.round((end - start) * fps)),
  });
  return (
    <SfxContext.Provider value={plan.sfx !== false}>
      <AbsoluteFill style={{backgroundColor: '#000'}}>
        <AbsoluteFill style={{width: W, height: H, transform: `scale(${width / W})`, transformOrigin: 'top left'}}>
          {plan.scenes
            .filter((s): s is SplitScene => s.type === 'split')
            .map((s) => {
              const q = seq(s.start, s.end);
              return (
                <Sequence key={s.id} {...q} name={`split ${s.id}`}>
                  <SplitBackground scene={s} dur={q.durationInFrames} />
                </Sequence>
              );
            })}
          <Avatar plan={plan} />
          {plan.scenes
            .filter((s) => s.type !== 'split')
            .map((s) => {
              const q = seq(s.start, s.end);
              return (
                <Sequence key={s.id} {...q} name={`${s.type} ${s.id}`}>
                  <SceneView scene={s} dur={q.durationInFrames} />
                </Sequence>
              );
            })}
          {plan.film !== false && <FilmLook />}
        </AbsoluteFill>
      </AbsoluteFill>
    </SfxContext.Provider>
  );
};
