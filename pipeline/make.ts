// One command: avatar video in -> finished video with overlays out.
//
//   npm run make -- input/video.mp4 [--job name] [--mode mixed|photos|graphics] [--provider pexels|fal|placeholder]
//                   [--force transcribe|plan|assets] [--no-render]
//
// Every step caches its result in work/<job>/ so you can hand-edit plan.json and re-run only the render.
import {execFileSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {parseArgs} from 'node:util';
import type {Plan} from '../src/types';
import {fetchAssets} from './assets';
import {emptyPlan, planScenes, sanitize, type Transcript} from './plan';
import {renderPlan} from './render';
import {OUT, PUBLIC, ROOT, WORK, loadSettings, type Mode, type Settings} from './settings';

const {values, positionals} = parseArgs({
  allowPositionals: true,
  options: {
    job: {type: 'string'},
    mode: {type: 'string'},
    provider: {type: 'string'},
    force: {type: 'string', multiple: true, default: []},
    'no-render': {type: 'boolean', default: false},
  },
});

const input = positionals[0];
if (!input) {
  console.error('usage: npm run make -- <video.mp4> [--job name] [--mode mixed|photos|graphics]');
  process.exit(1);
}
const s = loadSettings();
if (values.mode) s.mode = values.mode as Mode;
if (values.provider) s.imageProvider = values.provider as Settings['imageProvider'];
const job = values.job ?? path.basename(input, path.extname(input)).replace(/[^\w-]+/g, '_');
const dir = path.join(WORK, job);
fs.mkdirSync(dir, {recursive: true});
fs.mkdirSync(OUT, {recursive: true});
const force = new Set(values.force);
const readJson = <T>(f: string): T => JSON.parse(fs.readFileSync(f, 'utf8')) as T;
const writeJson = (f: string, v: unknown) => fs.writeFileSync(f, JSON.stringify(v, null, 1));

const probe = (file: string) => {
  const j = JSON.parse(
    execFileSync('ffprobe', ['-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=r_frame_rate,width,height:format=duration', '-of', 'json', file], {
      encoding: 'utf8',
    }),
  );
  const [n, d] = String(j.streams[0].r_frame_rate).split('/').map(Number);
  return {duration: Number(j.format.duration), fps: Math.round(n / (d || 1)), width: Number(j.streams[0].width), height: Number(j.streams[0].height)};
};

// 1. Put the avatar video where the renderer can read it.
const videoRel = `input/${job}${path.extname(input)}`;
const videoAbs = path.join(PUBLIC, videoRel);
fs.mkdirSync(path.dirname(videoAbs), {recursive: true});
if (!fs.existsSync(videoAbs)) fs.copyFileSync(path.resolve(input), videoAbs);
const src = probe(videoAbs);
const {duration, fps} = src;
console.log(`[${job}] ${duration.toFixed(1)} s @ ${fps} fps, mode=${s.mode}, images=${s.imageProvider}`);

// 2. Transcript with word timestamps.
const transcriptFile = path.join(dir, 'transcript.json');
if (!fs.existsSync(transcriptFile) || force.has('transcribe')) {
  console.log('transcribing...');
  const args = [path.join(ROOT, 'pipeline/transcribe.py'), videoAbs, transcriptFile, '--model', s.whisper.model, '--device', s.whisper.device, '--compute-type', s.whisper.computeType];
  if (s.whisper.language) args.push('--language', s.whisper.language);
  execFileSync('python3', args, {stdio: 'inherit'});
}
const transcript = readJson<Transcript>(transcriptFile);
transcript.duration = duration;

// 3. Scene plan (Claude). Hand-edit work/<job>/plan.json and re-run to tweak.
const planFile = path.join(dir, 'plan.json');
if (!fs.existsSync(planFile) || force.has('plan')) {
  console.log(`planning scenes with ${s.plannerModel}...`);
  const plan = emptyPlan(videoRel, src, s);
  plan.scenes = await planScenes(transcript, s);
  writeJson(planFile, plan);
  console.log(`plan: ${plan.scenes.length} scenes -> ${planFile}`);
}
const plan = readJson<Plan>(planFile);
plan.scenes = sanitize(plan.scenes, duration);

// 4. Assets (stock / generated). Cached per scene id.
const resolvedFile = path.join(dir, 'plan.resolved.json');
if (!fs.existsSync(resolvedFile) || force.has('assets') || fs.statSync(planFile).mtimeMs > fs.statSync(resolvedFile).mtimeMs) {
  console.log('fetching assets...');
  await fetchAssets(plan, job, s, force.has('assets'));
  writeJson(resolvedFile, plan);
}
const resolved = readJson<Plan>(resolvedFile);

// 5. Render.
if (!values['no-render']) {
  await renderPlan(resolved, path.join(OUT, `${job}.mp4`), s);
}
