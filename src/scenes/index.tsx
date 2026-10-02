import React, {createContext, useContext} from 'react';
import {AbsoluteFill, Audio, Sequence, interpolate, random, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import type {
  BoardScene,
  ChecklistScene,
  LabelScene,
  NoteScene,
  NumbersScene,
  PhotoScene,
  PolaroidsScene,
  QuoteScene,
  Scene,
  SplitScene,
  StampScene,
} from '../types';
import {progress, useIn, useOut} from '../ui/anim';
import {Backdrop, CaptionStrip, Media, Paper, RedCircle, Stamp, Typewriter, noise, typeFrames} from '../ui/kit';
import {C, HEAD, MONO} from '../ui/theme';

export const SfxContext = createContext(true);

type SfxName = 'whoosh' | 'click' | 'camera' | 'stamp';
const Sfx: React.FC<{name: SfxName; at?: number; volume?: number}> = ({name, at = 0, volume = 0.5}) =>
  useContext(SfxContext) ? (
    <Sequence from={Math.max(0, Math.round(at))} durationInFrames={30} layout="none">
      <Audio src={staticFile(`sfx/${name}.mp3`)} volume={volume} />
    </Sequence>
  ) : null;

type P<T> = {scene: T; dur: number};

/** Common fade in/out wrapper for scenes that cover the avatar. */
const Cover: React.FC<{dur: number; children: React.ReactNode}> = ({dur, children}) => {
  const frame = useCurrentFrame();
  const opacity = Math.min(progress(frame, 0, 5), useOut(dur, 6));
  return <AbsoluteFill style={{opacity}}>{children}</AbsoluteFill>;
};

const PhotoView: React.FC<P<PhotoScene>> = ({scene, dur}) => {
  const {fps} = useVideoConfig();
  const stampAt = Math.round(fps * 0.8);
  return (
    <Cover dur={dur}>
      <Media asset={scene.asset} grade={scene.grade} seed={scene.id} dur={dur} />
      {scene.circle && <RedCircle circle={scene.circle} from={Math.round(fps * 0.6)} />}
      {scene.caption && <CaptionStrip text={scene.caption} from={Math.round(fps * 0.4)} style={{left: 90, bottom: 90}} />}
      {scene.stamp && (
        <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center'}}>
          <Stamp text={scene.stamp} p={useIn(stampAt, 18)} size={110} />
        </AbsoluteFill>
      )}
      <Sfx name="whoosh" volume={0.35} />
      {scene.stamp && <Sfx name="stamp" at={stampAt} />}
    </Cover>
  );
};

/** Rendered *under* the avatar; the avatar layer shrinks to the opposite side (see Main). */
export const SplitBackground: React.FC<P<SplitScene>> = ({scene, dur}) => {
  const p = Math.min(useIn(2), useOut(dur, 10));
  const photoLeft = (scene.avatar ?? 'left') === 'right';
  return (
    <AbsoluteFill style={{backgroundColor: '#17140f', backgroundImage: noise(11, 0.7, 0.5), backgroundBlendMode: 'overlay'}}>
      <div
        style={{
          position: 'absolute',
          top: 150,
          width: 860,
          height: 700,
          left: photoLeft ? 70 : 990,
          background: '#f3efe6',
          padding: '22px 22px 90px',
          boxShadow: '0 20px 40px rgba(0,0,0,0.6)',
          transform: `translateY(${(1 - p) * 700}px) rotate(${photoLeft ? -2 : 2}deg)`,
        }}
      >
        <div style={{position: 'relative', width: '100%', height: '100%', overflow: 'hidden'}}>
          <Media asset={scene.asset} grade={scene.grade} seed={scene.id} dur={dur} />
        </div>
        {scene.caption && (
          <div
            style={{
              position: 'absolute',
              bottom: 24,
              left: 0,
              right: 0,
              textAlign: 'center',
              fontFamily: MONO,
              fontSize: 34,
              textTransform: 'uppercase',
              letterSpacing: 2,
              color: C.ink,
            }}
          >
            <Typewriter text={scene.caption} from={14} cursor={false} />
          </div>
        )}
      </div>
      <Sfx name="whoosh" volume={0.35} />
    </AbsoluteFill>
  );
};

const NoteView: React.FC<P<NoteScene>> = ({scene, dur}) => {
  const {fps} = useVideoConfig();
  const enter = useIn(0);
  let t = Math.round(fps * 0.4);
  const starts = scene.lines.map((l) => {
    const s = t;
    t += typeFrames(l, fps) + 4;
    return s;
  });
  const stampAt = t + 6;
  const h = 200 + scene.lines.length * 62 + (scene.title ? 80 : 0);
  return (
    <Cover dur={dur}>
      <Backdrop asset={scene.bg} grade={scene.grade} seed={scene.id} dur={dur} />
      <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center'}}>
        <Paper w={1150} h={h} seed={scene.id} style={{position: 'relative', transform: `translateY(${(1 - enter) * 900}px) rotate(-1deg)`}}>
          {scene.title && (
            <div style={{fontFamily: HEAD, fontWeight: 700, fontSize: 54, textTransform: 'uppercase', marginBottom: 26, color: C.red}}>
              {scene.title}
            </div>
          )}
          {scene.lines.map((l, i) => (
            <div key={i} style={{fontSize: 38, lineHeight: '62px'}}>
              <Typewriter text={l} from={starts[i]} cursor={i === scene.lines.length - 1 || useCurrentFrame() < (starts[i + 1] ?? 0)} />
            </div>
          ))}
          {scene.stamp && <Stamp text={scene.stamp} p={useIn(stampAt, 18)} size={64} rotate={-14} style={{right: 40, bottom: 30}} />}
        </Paper>
      </AbsoluteFill>
      <Sfx name="whoosh" volume={0.3} />
      {starts.map((s, i) => (
        <Sfx key={i} name="click" at={s} volume={0.35} />
      ))}
      {scene.stamp && <Sfx name="stamp" at={stampAt} />}
    </Cover>
  );
};

const QuoteView: React.FC<P<QuoteScene>> = ({scene, dur}) => {
  const {fps} = useVideoConfig();
  const enter = useIn(0);
  const from = Math.round(fps * 0.4);
  const authorAt = from + typeFrames(scene.text, fps, 32) + 6;
  return (
    <Cover dur={dur}>
      <Backdrop asset={scene.bg} grade={scene.grade} seed={scene.id} dur={dur} />
      <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center'}}>
        <Paper w={1100} h={420} seed={scene.id} style={{position: 'relative', transform: `translateY(${(1 - enter) * 800}px) rotate(1.5deg)`}}>
          <div style={{fontSize: 46, lineHeight: 1.35}}>
            <Typewriter text={`«${scene.text}»`} from={from} cps={32} />
          </div>
          {scene.author && (
            <div style={{marginTop: 30, fontSize: 28, color: C.red, opacity: progress(useCurrentFrame(), authorAt, authorAt + 8)}}>
              — {scene.author}
            </div>
          )}
        </Paper>
      </AbsoluteFill>
      <Sfx name="click" at={from} volume={0.35} />
    </Cover>
  );
};

const ChecklistView: React.FC<P<ChecklistScene>> = ({scene, dur}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const enter = useIn(0);
  const n = scene.items.length;
  const gap = Math.max(fps * 0.6, (dur - fps * 1.2) / Math.max(1, n));
  const at = (i: number) => Math.round(fps * 0.5 + i * gap);
  return (
    <Cover dur={dur}>
      <Backdrop asset={scene.bg} grade={scene.grade} seed={scene.id} dur={dur} />
      <Paper w={900} h={170 + n * 92} seed={scene.id} style={{left: 140, top: 140, transform: `translateX(${(enter - 1) * 1200}px) rotate(-1deg)`}}>
        {scene.items.map((item, i) => {
          const p = progress(frame, at(i), at(i) + 6);
          const x = progress(frame, at(i) + 4, at(i) + 10);
          return (
            <div key={i} style={{display: 'flex', alignItems: 'center', gap: 28, height: 92, opacity: p}}>
              <svg width={46} height={46} viewBox="0 0 46 46">
                <rect x={3} y={3} width={40} height={40} fill="none" stroke={C.ink} strokeWidth={3} />
                <path d="M10 10 L36 36" stroke={C.red} strokeWidth={5} strokeLinecap="round" strokeDasharray={38} strokeDashoffset={38 * (1 - x)} />
                <path d="M36 10 L10 36" stroke={C.red} strokeWidth={5} strokeLinecap="round" strokeDasharray={38} strokeDashoffset={38 * (1 - x)} />
              </svg>
              <div style={{fontSize: 40}}>
                <Typewriter text={item} from={at(i)} cursor={false} cps={34} />
              </div>
            </div>
          );
        })}
      </Paper>
      <Sfx name="whoosh" volume={0.3} />
      {scene.items.map((_, i) => (
        <Sfx key={i} name="click" at={at(i) + 4} volume={0.45} />
      ))}
    </Cover>
  );
};

const fmt = (v: number, decimals = 0) =>
  v.toLocaleString('ru-RU', {minimumFractionDigits: decimals, maximumFractionDigits: decimals});

const NumbersView: React.FC<P<NumbersScene>> = ({scene, dur}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const n = scene.items.length;
  const w = n === 1 ? 640 : 420;
  return (
    <Cover dur={dur}>
      <Backdrop asset={scene.bg} grade={scene.grade} seed={scene.id} dur={dur} dim={0.25} />
      <AbsoluteFill style={{flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 60}}>
        {scene.items.map((it, i) => {
          const delay = i * 8;
          const p = useIn(delay, 12);
          const count = interpolate(frame, [delay + 4, delay + fps * 1.4], [0, it.value], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
            easing: (t) => 1 - Math.pow(1 - t, 3),
          });
          return (
            <Paper
              key={i}
              w={w}
              h={340}
              seed={`${scene.id}-${i}`}
              style={{position: 'relative', transform: `translateY(${(1 - p) * 700}px) rotate(${(random(`${scene.id}${i}`) - 0.5) * 6}deg)`}}
            >
              <div style={{textAlign: 'center', fontFamily: HEAD, fontWeight: 700, fontSize: n === 1 ? 170 : 140, color: C.red, lineHeight: 1}}>
                {it.prefix}
                {fmt(count, it.decimals)}
                {it.suffix}
              </div>
              <div style={{textAlign: 'center', fontSize: 28, marginTop: 24, textTransform: 'uppercase', letterSpacing: 1}}>{it.label}</div>
            </Paper>
          );
        })}
      </AbsoluteFill>
      {scene.items.map((_, i) => (
        <Sfx key={i} name="whoosh" at={i * 8} volume={0.3} />
      ))}
    </Cover>
  );
};

const PolaroidsView: React.FC<P<PolaroidsScene>> = ({scene, dur}) => {
  const {fps} = useVideoConfig();
  const n = scene.items.length;
  const gap = Math.min(fps * 0.9, (dur * 0.6) / Math.max(1, n));
  const w = n <= 2 ? 620 : n === 3 ? 520 : 420;
  const spread = 1920 / n;
  return (
    <Cover dur={dur}>
      <Backdrop asset={scene.bg} grade={scene.grade} seed={scene.id} dur={dur} />
      {scene.items.map((it, i) => {
        const at = Math.round(i * gap);
        const p = useIn(at, 13);
        const rot = (random(`${scene.id}-r${i}`) - 0.5) * 10;
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: spread * i + spread / 2 - w / 2,
              top: 170 + (random(`${scene.id}-y${i}`) - 0.5) * 80,
              width: w,
              height: w * 1.12,
              background: '#f3efe6',
              padding: `${w * 0.045}px ${w * 0.045}px ${w * 0.2}px`,
              boxShadow: '0 18px 36px rgba(0,0,0,0.6)',
              transform: `translateY(${(1 - p) * 1100}px) rotate(${rot + (1 - p) * 20}deg)`,
            }}
          >
            <div style={{position: 'relative', width: '100%', height: '100%', overflow: 'hidden'}}>
              <Media asset={it.asset} grade={scene.grade} seed={`${scene.id}-${i}`} dur={dur} />
            </div>
            <div
              style={{
                position: 'absolute',
                left: 0,
                right: 0,
                bottom: w * 0.06,
                textAlign: 'center',
                fontFamily: MONO,
                fontSize: Math.round(w * 0.06),
                textTransform: 'uppercase',
                letterSpacing: 2,
                color: C.ink,
              }}
            >
              <Typewriter text={it.caption} from={at + 10} cursor={false} />
            </div>
          </div>
        );
      })}
      {scene.label && (
        <CaptionStrip text={scene.label} from={Math.round(n * gap + 6)} style={{left: '50%', bottom: 70, transform: 'translateX(-50%)'}} size={34} />
      )}
      {scene.items.map((_, i) => (
        <Sfx key={i} name="camera" at={Math.round(i * gap) + 4} volume={0.5} />
      ))}
    </Cover>
  );
};

const StampView: React.FC<P<StampScene>> = ({scene, dur}) => {
  const {fps} = useVideoConfig();
  const at = Math.round(fps * 0.3);
  return (
    <Cover dur={dur}>
      <Backdrop asset={scene.bg} grade={scene.grade} seed={scene.id} dur={dur} dim={0.2} />
      <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center'}}>
        <Stamp text={scene.text} p={useIn(at, 18)} size={150} />
      </AbsoluteFill>
      <Sfx name="stamp" at={at} volume={0.7} />
    </Cover>
  );
};

/** Lower third over the avatar. */
const LabelView: React.FC<P<LabelScene>> = ({scene, dur}) => {
  const p = Math.min(useIn(0), useOut(dur, 8));
  return (
    <AbsoluteFill>
      <Paper
        w={720}
        h={scene.sub ? 170 : 120}
        seed={scene.id}
        style={{left: 110, bottom: 110, transform: `translateX(${(p - 1) * 900}px) rotate(-1.5deg)`}}
      >
        <div style={{marginTop: -18, fontFamily: HEAD, fontWeight: 700, fontSize: 52, lineHeight: 1.1}}>{scene.text}</div>
        {scene.sub && (
          <div style={{fontSize: 24, color: C.red, marginTop: 8, textTransform: 'uppercase', letterSpacing: 1}}>
            <Typewriter text={scene.sub} from={10} cursor={false} />
          </div>
        )}
      </Paper>
      <Sfx name="whoosh" volume={0.3} />
    </AbsoluteFill>
  );
};

const BOARD_SLOTS = [
  {x: 120, y: 90},
  {x: 1380, y: 70},
  {x: 140, y: 600},
  {x: 1360, y: 590},
  {x: 760, y: 40},
  {x: 760, y: 690},
];

const BoardView: React.FC<P<BoardScene>> = ({scene, dur}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const items = scene.items.slice(0, BOARD_SLOTS.length);
  const gap = Math.round(fps * 0.5);
  const cx = 960;
  const cy = 520;
  const centerAt = items.length * gap;
  return (
    <Cover dur={dur}>
      <AbsoluteFill
        style={{
          backgroundColor: '#8a6a45',
          backgroundImage: `${noise(21, 0.55, 0.9)}, radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,0.6) 100%)`,
          backgroundBlendMode: 'multiply',
        }}
      />
      <svg width={1920} height={1080} style={{position: 'absolute', inset: 0}}>
        {items.map((_, i) => {
          const s = BOARD_SLOTS[i];
          const x = s.x + 200;
          const y = s.y + 170;
          const len = Math.hypot(x - cx, y - cy);
          const p = progress(frame, centerAt + i * 4, centerAt + i * 4 + 12);
          return (
            <line
              key={i}
              x1={cx}
              y1={cy}
              x2={x}
              y2={y}
              stroke={C.red}
              strokeWidth={4}
              strokeDasharray={len}
              strokeDashoffset={len * (1 - p)}
            />
          );
        })}
      </svg>
      {items.map((it, i) => {
        const s = BOARD_SLOTS[i];
        const p = useIn(i * gap, 13);
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: s.x,
              top: s.y,
              width: 400,
              height: 340,
              background: '#f3efe6',
              padding: '16px 16px 64px',
              boxShadow: '0 14px 28px rgba(0,0,0,0.55)',
              opacity: p,
              transform: `scale(${1.3 - 0.3 * p}) rotate(${(random(`${scene.id}b${i}`) - 0.5) * 8}deg)`,
            }}
          >
            <div style={{position: 'relative', width: '100%', height: '100%', overflow: 'hidden'}}>
              <Media asset={it.asset} grade="sepia" seed={`${scene.id}-${i}`} dur={dur} />
            </div>
            <div style={{position: 'absolute', bottom: 14, left: 0, right: 0, textAlign: 'center', fontFamily: MONO, fontSize: 26, textTransform: 'uppercase'}}>
              {it.caption}
            </div>
            <div style={{position: 'absolute', top: -10, left: 188, width: 22, height: 22, borderRadius: 11, background: C.red, boxShadow: '0 3px 4px rgba(0,0,0,0.5)'}} />
          </div>
        );
      })}
      <Paper w={240} h={240} seed={`${scene.id}-c`} tape={false} style={{left: cx - 120, top: cy - 120, transform: `scale(${useIn(centerAt, 12)})`}}>
        <div style={{fontFamily: HEAD, fontWeight: 700, fontSize: 130, color: C.red, textAlign: 'center', marginTop: -26}}>{scene.center ?? '?'}</div>
      </Paper>
      {scene.label && <CaptionStrip text={scene.label} from={centerAt + 20} style={{left: '50%', bottom: 50, transform: 'translateX(-50%)'}} size={40} />}
      {items.map((_, i) => (
        <Sfx key={i} name="camera" at={i * gap + 2} volume={0.45} />
      ))}
    </Cover>
  );
};

/** Scenes drawn above the avatar layer. `split` is handled separately (under the avatar). */
export const SceneView: React.FC<{scene: Scene; dur: number}> = ({scene, dur}) => {
  switch (scene.type) {
    case 'photo':
      return <PhotoView scene={scene} dur={dur} />;
    case 'note':
      return <NoteView scene={scene} dur={dur} />;
    case 'quote':
      return <QuoteView scene={scene} dur={dur} />;
    case 'checklist':
      return <ChecklistView scene={scene} dur={dur} />;
    case 'numbers':
      return <NumbersView scene={scene} dur={dur} />;
    case 'polaroids':
      return <PolaroidsView scene={scene} dur={dur} />;
    case 'stamp':
      return <StampView scene={scene} dur={dur} />;
    case 'label':
      return <LabelView scene={scene} dur={dur} />;
    case 'board':
      return <BoardView scene={scene} dur={dur} />;
    case 'split':
      return null;
  }
};
