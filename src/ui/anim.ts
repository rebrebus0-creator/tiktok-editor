import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';

/** 0 -> 1 spring at `delay` frames into the current Sequence. */
export const useIn = (delay = 0, damping = 14): number => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  return spring({frame: frame - delay, fps, config: {damping, mass: 0.7}});
};

/** 1 while on screen, ramps to 0 over the last `len` frames of a Sequence lasting `dur` frames. */
export const useOut = (dur: number, len = 8): number => {
  const frame = useCurrentFrame();
  return interpolate(frame, [dur - len, dur], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
};

/** Linear 0..1 progress between two frames, clamped. */
export const progress = (frame: number, from: number, to: number): number =>
  interpolate(frame, [from, to], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
