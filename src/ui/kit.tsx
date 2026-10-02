import React from 'react';
import {
  AbsoluteFill,
  Img,
  OffthreadVideo,
  interpolate,
  random,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import type {Asset, Circle, Grade} from '../types';
import {progress} from './anim';
import {C, HEAD, MONO, gradeFilter} from './theme';

export const resolveSrc = (src: string): string =>
  /^(https?:|data:|blob:)/.test(src) ? src : staticFile(src);

export const noise = (seed: number, freq = 0.8, opacity = 1): string =>
  `url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='300' height='300'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='${freq}' numOctaves='3' seed='${seed}' stitchTiles='stitch'/><feColorMatrix type='saturate' values='0'/></filter><rect width='100%25' height='100%25' filter='url(%23n)' opacity='${opacity}'/></svg>")`;

/** Polygon with jittered edges so the sheet looks torn. */
const tornClip = (w: number, h: number, seed: string, amp = 5): string => {
  const pts: string[] = [];
  const step = 22;
  const j = (i: number) => (random(`${seed}-${i}`) - 0.5) * 2 * amp;
  let i = 0;
  for (let x = 0; x <= w; x += step) pts.push(`${x}px ${Math.max(0, amp + j(i++))}px`);
  for (let y = 0; y <= h; y += step) pts.push(`${w - Math.max(0, amp + j(i++))}px ${y}px`);
  for (let x = w; x >= 0; x -= step) pts.push(`${x}px ${h - Math.max(0, amp + j(i++))}px`);
  for (let y = h; y >= 0; y -= step) pts.push(`${Math.max(0, amp + j(i++))}px ${y}px`);
  return `polygon(${pts.join(',')})`;
};

export const Tape: React.FC<{style?: React.CSSProperties; rotate?: number}> = ({style, rotate = -35}) => (
  <div
    style={{
      position: 'absolute',
      width: 120,
      height: 36,
      background: C.tape,
      boxShadow: '0 1px 3px rgba(0,0,0,0.25)',
      transform: `rotate(${rotate}deg)`,
      ...style,
    }}
  />
);

export const Paper: React.FC<{
  w: number;
  h: number;
  seed: string;
  tape?: boolean;
  style?: React.CSSProperties;
  children?: React.ReactNode;
}> = ({w, h, seed, tape = true, style, children}) => (
  <div style={{position: 'absolute', width: w, height: h, filter: 'drop-shadow(0 14px 22px rgba(0,0,0,0.55))', ...style}}>
    <div
      style={{
        position: 'absolute',
        inset: 0,
        clipPath: tornClip(w, h, seed),
        backgroundColor: C.paper,
        backgroundImage: `radial-gradient(ellipse at center, rgba(255,250,235,0.5) 0%, rgba(120,90,40,0.28) 100%), ${noise(Math.floor(random(seed) * 100), 0.9, 0.35)}`,
        backgroundBlendMode: 'multiply',
      }}
    />
    <div style={{position: 'absolute', inset: 0, padding: '48px 56px', color: C.ink, fontFamily: MONO}}>{children}</div>
    {tape && (
      <>
        <Tape style={{left: -38, top: -6}} rotate={-38} />
        <Tape style={{right: -38, bottom: -4}} rotate={-38} />
      </>
    )}
  </div>
);

/** Red rubber stamp. `p` is the 0..1 slam-in progress. */
export const Stamp: React.FC<{text: string; p: number; size?: number; rotate?: number; style?: React.CSSProperties}> = ({
  text,
  p,
  size = 120,
  rotate = -7,
  style,
}) => {
  const scale = interpolate(p, [0, 1], [2.2, 1]);
  return (
    <div
      style={{
        position: 'absolute',
        transform: `rotate(${rotate}deg) scale(${scale})`,
        opacity: interpolate(p, [0, 0.3], [0, 0.92], {extrapolateRight: 'clamp'}),
        border: `${size * 0.07}px solid ${C.red}`,
        outline: `${size * 0.025}px solid ${C.red}`,
        outlineOffset: size * 0.06,
        padding: `${size * 0.02}px ${size * 0.22}px`,
        color: C.red,
        fontFamily: HEAD,
        fontWeight: 700,
        fontSize: size,
        lineHeight: 1.15,
        textTransform: 'uppercase',
        whiteSpace: 'nowrap',
        WebkitMaskImage: noise(7, 0.65),
        WebkitMaskSize: '300px 300px',
        mixBlendMode: 'multiply',
        ...style,
      }}
    >
      {text}
    </div>
  );
};

/**
 * Typewriter text. Characters appear from `from` frame at `cps` chars/second.
 * [[words]] are redacted: they become black bars once typed.
 */
export const Typewriter: React.FC<{text: string; from?: number; cps?: number; cursor?: boolean; style?: React.CSSProperties}> = ({
  text,
  from = 0,
  cps = 28,
  cursor = true,
  style,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const shown = Math.max(0, Math.floor(((frame - from) / fps) * cps));
  const parts = text.split(/(\[\[.*?\]\])/g).filter(Boolean);
  let budget = shown;
  let total = 0;
  const out: React.ReactNode[] = [];
  parts.forEach((part, i) => {
    const redacted = part.startsWith('[[');
    const body = redacted ? part.slice(2, -2) : part;
    total += body.length;
    if (budget <= 0) return;
    const vis = body.slice(0, budget);
    budget -= body.length;
    out.push(
      redacted ? (
        <span key={i} style={{background: '#111', color: 'transparent', boxDecorationBreak: 'clone'}}>
          {vis}
        </span>
      ) : (
        <span key={i}>{vis}</span>
      ),
    );
  });
  const typing = shown < total;
  const blink = Math.floor(frame / (fps / 3)) % 2 === 0;
  return (
    <span style={{whiteSpace: 'pre-wrap', ...style}}>
      {out}
      {cursor && frame >= from && (typing || blink) ? '_' : ''}
    </span>
  );
};

/** Frames needed to type `text` at `cps`. */
export const typeFrames = (text: string, fps: number, cps = 28): number =>
  Math.ceil((text.replace(/\[\[|\]\]/g, '').length / cps) * fps);

/** Image (with slow Ken Burns) or muted video, color-graded. Falls back to a placeholder card. */
export const Media: React.FC<{asset?: Asset; grade?: Grade; seed: string; dur: number; style?: React.CSSProperties}> = ({
  asset,
  grade,
  seed,
  dur,
  style,
}) => {
  const frame = useCurrentFrame();
  const t = progress(frame, 0, dur);
  const dir = random(seed) > 0.5 ? 1 : -1;
  const zoomIn = random(`${seed}z`) > 0.4;
  const scale = zoomIn ? 1.04 + 0.12 * t : 1.16 - 0.12 * t;
  const tx = dir * (t - 0.5) * 3;
  const filter = gradeFilter(grade);
  const box: React.CSSProperties = {width: '100%', height: '100%', objectFit: 'cover', filter};
  if (!asset?.src) {
    return (
      <AbsoluteFill
        style={{
          background: 'radial-gradient(ellipse at 40% 35%, #3b4250 0%, #14161b 75%)',
          alignItems: 'center',
          justifyContent: 'center',
          ...style,
        }}
      >
        <div style={{fontFamily: MONO, color: 'rgba(255,255,255,0.35)', fontSize: 34, maxWidth: '70%', textAlign: 'center'}}>
          [ {asset?.query ?? asset?.prompt ?? 'изображение'} ]
        </div>
      </AbsoluteFill>
    );
  }
  const src = resolveSrc(asset.src);
  return (
    <AbsoluteFill style={{overflow: 'hidden', ...style}}>
      <AbsoluteFill style={{transform: `scale(${scale}) translateX(${tx}%)`}}>
        {asset.kind === 'video' ? <OffthreadVideo src={src} muted style={box} /> : <Img src={src} style={box} />}
      </AbsoluteFill>
      {grade === 'cold' && <AbsoluteFill style={{background: '#2b5d9e', mixBlendMode: 'soft-light', opacity: 0.75}} />}
    </AbsoluteFill>
  );
};

/** Hand-drawn red circle that draws itself. Coordinates are relative to the parent box. */
export const RedCircle: React.FC<{circle: Circle; from?: number; len?: number}> = ({circle, from = 0, len = 14}) => {
  const frame = useCurrentFrame();
  const p = progress(frame, from, from + len);
  const {x, y, r} = circle;
  // Slightly more than a full turn, with a wobble, like a marker stroke.
  const pts: string[] = [];
  const turns = 1.12;
  const n = 64;
  for (let i = 0; i <= n; i++) {
    const a = -Math.PI / 2 + (i / n) * Math.PI * 2 * turns;
    const k = 1 + 0.06 * Math.sin(i * 0.7) + 0.04 * (i / n);
    pts.push(`${(x + Math.cos(a) * r * 1.25 * k) * 1000},${(y + Math.sin(a) * r * k * 1.78) * 562.5}`);
  }
  const length = 2 * Math.PI * r * 1000 * 1.6 * turns;
  return (
    <svg viewBox="0 0 1000 562.5" preserveAspectRatio="none" style={{position: 'absolute', inset: 0, width: '100%', height: '100%'}}>
      <polyline
        points={pts.join(' ')}
        fill="none"
        stroke={C.red}
        strokeWidth={5}
        strokeLinecap="round"
        strokeDasharray={length}
        strokeDashoffset={length * (1 - p)}
        style={{filter: 'drop-shadow(0 0 2px rgba(0,0,0,0.5))'}}
      />
    </svg>
  );
};

/** Small paper strip with a typed caption (used under photos and as a lower third). */
export const CaptionStrip: React.FC<{text: string; from?: number; style?: React.CSSProperties; size?: number}> = ({
  text,
  from = 0,
  style,
  size = 30,
}) => {
  const p = progress(useCurrentFrame(), from, from + 6);
  return (
    <div
      style={{
        position: 'absolute',
        background: C.paper,
        backgroundImage: noise(3, 0.9, 0.25),
        backgroundBlendMode: 'multiply',
        padding: `${size * 0.35}px ${size * 0.8}px`,
        boxShadow: '0 6px 14px rgba(0,0,0,0.5)',
        fontFamily: MONO,
        fontSize: size,
        letterSpacing: 2,
        textTransform: 'uppercase',
        color: C.red,
        opacity: p,
        transform: `translateY(${(1 - p) * 20}px) rotate(-1deg)`,
        ...style,
      }}
    >
      <Typewriter text={text} from={from + 4} cps={24} cursor={false} />
    </div>
  );
};

/** Grain + vignette + rounded old-film frame over the whole picture. */
export const FilmLook: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <AbsoluteFill
        style={{
          backgroundImage: noise(Math.floor(frame / 2) % 12, 0.85),
          backgroundSize: '300px 300px',
          opacity: 0.09,
          mixBlendMode: 'overlay',
        }}
      />
      <AbsoluteFill style={{background: 'radial-gradient(ellipse at center, transparent 55%, rgba(0,0,0,0.55) 100%)'}} />
      <AbsoluteFill
        style={{
          inset: 10,
          borderRadius: 26,
          boxShadow: '0 0 0 60px #050505, inset 0 0 40px rgba(0,0,0,0.75)',
        }}
      />
    </AbsoluteFill>
  );
};

/** Dimmed backdrop: either the given asset or a dark veil over whatever is below (the avatar). */
export const Backdrop: React.FC<{asset?: Asset; grade?: Grade; seed: string; dur: number; dim?: number}> = ({
  asset,
  grade,
  seed,
  dur,
  dim = 0.35,
}) => (
  <AbsoluteFill>
    {asset ? <Media asset={asset} grade={grade} seed={seed} dur={dur} /> : <AbsoluteFill style={{backdropFilter: 'blur(14px)'}} />}
    <AbsoluteFill style={{background: `rgba(0,0,0,${asset ? dim : 0.55})`}} />
  </AbsoluteFill>
);
