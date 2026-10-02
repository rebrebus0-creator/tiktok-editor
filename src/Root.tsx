import React from 'react';
import {Composition} from 'remotion';
import {Main} from './Main';
import demo from './demo-plan.json';
import type {Plan} from './types';

export const Root: React.FC = () => (
  <Composition
    id="Main"
    component={Main}
    defaultProps={demo as Plan}
    width={1920}
    height={1080}
    fps={24}
    durationInFrames={240}
    calculateMetadata={({props}) => ({
      fps: props.fps,
      width: props.width,
      height: props.height,
      durationInFrames: Math.max(1, Math.round(props.duration * props.fps)),
    })}
  />
);
