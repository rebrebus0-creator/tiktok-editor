import fs from 'node:fs';
import path from 'node:path';

export const ROOT = path.resolve(import.meta.dirname, '..');
export const PUBLIC = path.join(ROOT, 'public');
export const WORK = path.join(ROOT, 'work');
export const OUT = path.join(ROOT, 'out');

/** What the planner is allowed to put on screen. */
export type Mode = 'mixed' | 'photos' | 'graphics';

export type Settings = {
  mode: Mode;
  /** Where images come from: stock search, an image generator, or offline placeholders. */
  imageProvider: 'pexels' | 'fal' | 'placeholder';
  /** Allow short stock video clips (Pexels) in place of photos. */
  stockVideo: boolean;
  /** Language of the on-screen text. Default: the transcript language. */
  textLanguage?: string;
  /** Visual style hint passed to the planner and to the image generator. */
  styleHint: string;
  pexelsApiKey?: string;
  fal?: {apiKey?: string; model: string};
  whisper: {model: string; device: string; computeType: string; language?: string};
  /** Claude model used to plan scenes. */
  plannerModel: string;
  /** width/height default to the source video size. */
  render: {width?: number; height?: number; concurrency: number; crf: number; browserExecutable?: string};
  film: boolean;
  sfx: boolean;
};

const DEFAULTS: Settings = {
  mode: 'mixed',
  imageProvider: 'pexels',
  stockVideo: true,
  styleHint:
    'Documentary "case file" look: torn paper notes with tape, typewriter text, red rubber stamps, polaroids, red marker circles, old-film grain.',
  fal: {model: 'fal-ai/flux/schnell'},
  whisper: {model: 'small', device: 'cpu', computeType: 'int8'},
  plannerModel: 'claude-opus-5-5',
  render: {concurrency: 4, crf: 20},
  film: true,
  sfx: true,
};

/** settings.json (gitignored) overrides defaults; env vars override API keys. */
export const loadSettings = (): Settings => {
  const file = path.join(ROOT, 'settings.json');
  const user = fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf8')) : {};
  const s: Settings = {
    ...DEFAULTS,
    ...user,
    fal: {...DEFAULTS.fal!, ...user.fal},
    whisper: {...DEFAULTS.whisper, ...user.whisper},
    render: {...DEFAULTS.render, ...user.render},
  };
  s.pexelsApiKey = process.env.PEXELS_API_KEY ?? s.pexelsApiKey;
  if (process.env.FAL_KEY) s.fal = {...s.fal!, apiKey: process.env.FAL_KEY};
  return s;
};
