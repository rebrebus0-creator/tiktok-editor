// Transcript -> scene plan, using Claude.
import Anthropic from '@anthropic-ai/sdk';
import {z} from 'zod';
import type {Plan, Scene} from '../src/types';
import type {Mode, Settings} from './settings';

export type Transcript = {
  language: string;
  duration: number;
  segments: {start: number; end: number; text: string; words?: {start: number; end: number; word: string}[]}[];
};

const asset = z.object({
  query: z.string().optional(),
  prompt: z.string().optional(),
  kind: z.enum(['image', 'video']).optional(),
});
const grade = z.enum(['none', 'cold', 'sepia', 'bw']).optional();
const base = {id: z.string(), start: z.number(), end: z.number()};

const SceneSchema = z.discriminatedUnion('type', [
  z.object({...base, type: z.literal('photo'), asset, grade, caption: z.string().optional(), circle: z.object({x: z.number(), y: z.number(), r: z.number()}).optional(), stamp: z.string().optional()}),
  z.object({...base, type: z.literal('split'), asset, grade, avatar: z.enum(['left', 'right']).optional(), caption: z.string().optional()}),
  z.object({...base, type: z.literal('note'), lines: z.array(z.string()).min(1), title: z.string().optional(), stamp: z.string().optional(), bg: asset.optional(), grade}),
  z.object({...base, type: z.literal('quote'), text: z.string(), author: z.string().optional(), bg: asset.optional(), grade}),
  z.object({...base, type: z.literal('checklist'), items: z.array(z.string()).min(1).max(5), bg: asset.optional(), grade}),
  z.object({
    ...base,
    type: z.literal('numbers'),
    items: z.array(z.object({value: z.number(), label: z.string(), prefix: z.string().optional(), suffix: z.string().optional(), decimals: z.number().optional()})).min(1).max(3),
    bg: asset.optional(),
    grade,
  }),
  z.object({...base, type: z.literal('polaroids'), items: z.array(z.object({asset, caption: z.string()})).min(2).max(4), label: z.string().optional(), bg: asset.optional(), grade}),
  z.object({...base, type: z.literal('stamp'), text: z.string(), bg: asset.optional(), grade}),
  z.object({...base, type: z.literal('label'), text: z.string(), sub: z.string().optional()}),
  z.object({...base, type: z.literal('board'), items: z.array(z.object({asset, caption: z.string()})).min(3).max(6), center: z.string().optional(), label: z.string().optional()}),
]);
const PlanSchema = z.object({scenes: z.array(SceneSchema)});

const MODE_RULES: Record<Mode, string> = {
  mixed:
    'Combine photo-driven scenes (photo, split, polaroids, board, and backgrounds behind notes) with pure graphics (numbers, checklist, note, quote, stamp, label). Graphics should cover roughly 55-65% of the runtime.',
  photos:
    'Mostly photo, split and polaroids scenes, so pictures cover roughly 70-80% of the runtime and the avatar shows up between them. Use graphics only where a number or a short list is actually spoken.',
  graphics:
    'Do NOT use any images: no photo, split, polaroids or board scenes, and no `bg` fields. Use only note, quote, checklist, numbers, stamp and label (they will be drawn over a dimmed avatar). Cover roughly 40-50% of the runtime.',
};

const systemPrompt = (s: Settings, lang: string) => `You are a video editor planning motion-graphics overlays for a talking-avatar video (16:9).
You receive the transcript with timestamps (seconds). Output a JSON object {"scenes": [...]} and nothing else.

Visual style: ${s.styleHint}

Scene types (fields in addition to id, type, start, end):
- photo: full-screen picture. asset, grade?, caption? (short place/object name), circle? ({x,y,r} relative 0..1, only when pointing at something specific is natural), stamp? (1-2 words).
- split: avatar shrinks to one side, a framed picture on the other. asset, avatar? ("left"|"right"), caption?, grade?.
- note: torn paper with typed lines. lines (1-4 short lines, <= 40 chars each), title?, stamp?, bg?. Wrap a word in [[double brackets]] to redact it (for secrets/hidden facts).
- quote: a quotation actually said or cited. text, author?, bg?.
- checklist: 2-5 short facts ticked one by one. items, bg?.
- numbers: 1-3 big counting numbers. items [{value, label, prefix?, suffix?, decimals?}]. Only for numbers actually spoken.
- polaroids: 2-4 photos with captions appearing one by one. items [{asset, caption}], label?.
- stamp: one big red stamp word/date over a picture. text (1-3 words or a date), bg?.
- label: lower-third paper strip over the avatar (does not hide it). text (<= 28 chars), sub? (<= 40 chars). Good for the topic intro, names, places, dates.
- board: investigation board with 3-6 photos linked to a central card. items, center? (default "?"), label?. At most once, for a recap or a finale.

Assets: {"query": "...", "kind": "image"|"video"?, "prompt": "..."}.
- query: 2-5 English words for a stock search, concrete and visual ("old fishing boat at dawn", not "tradition").
- prompt: one English sentence for an image generator: photorealistic, documentary, describe subject, setting, light; no text or letters in the image.
- kind "video" only for scenes that clearly benefit from motion${s.stockVideo ? '' : ' (stock video is disabled: always omit kind)'}.
- grade: "cold" for night/winter/mystery, "sepia" for history/archives, "bw" for old events, otherwise "none".

Mode: ${MODE_RULES[s.mode]}

Timing rules:
- Start a scene on the word where its idea is spoken (use the timestamps); typical length 3-7 s, never shorter than 2.5 s or longer than 10 s.
- Scenes must not overlap; leave at least 0.3 s between them.
- Keep the avatar visible for the first 3 s and for at least 2 s between consecutive full-screen scenes. Never hide the avatar for more than ~25 s in a row.
- Vary the scene types; do not repeat the same type more than twice in a row.
- ids: "s001", "s002", ... in time order.

All on-screen text in ${lang}. Keep it short and punchy: on-screen text summarises, it never repeats the whole sentence.`;

const fmtTranscript = (t: Transcript) =>
  t.segments.map((s) => `[${s.start.toFixed(1)}-${s.end.toFixed(1)}] ${s.text}`).join('\n');

const extractJson = (text: string): unknown => {
  const a = text.indexOf('{');
  const b = text.lastIndexOf('}');
  if (a < 0 || b < a) throw new Error('no JSON object in the response');
  return JSON.parse(text.slice(a, b + 1));
};

/** Sort, clamp to the video and drop overlaps the model may have produced. */
export const sanitize = (scenes: Scene[], duration: number): Scene[] => {
  const out: Scene[] = [];
  for (const s of [...scenes].sort((x, y) => x.start - y.start)) {
    const prev = out[out.length - 1];
    const start = Math.max(s.start, prev ? prev.end + 0.3 : 0);
    const end = Math.min(s.end, duration - 0.1);
    if (end - start >= 2) out.push({...s, start: +start.toFixed(2), end: +end.toFixed(2)});
  }
  return out;
};

export const planScenes = async (t: Transcript, s: Settings): Promise<Scene[]> => {
  const client = new Anthropic();
  const lang = s.textLanguage ?? t.language;
  const messages: Anthropic.Beta.BetaMessageParam[] = [
    {role: 'user', content: `Video duration: ${t.duration.toFixed(1)} s.\n\nTranscript:\n${fmtTranscript(t)}`},
  ];
  for (let attempt = 0; attempt < 3; attempt++) {
    const stream = client.beta.messages.stream({
      model: s.plannerModel,
      max_tokens: 64000,
      thinking: {type: 'adaptive'},
      output_config: {effort: 'high'},
      betas: ['server-side-fallback-2026-07-01'],
      fallbacks: 'default',
      system: systemPrompt(s, lang),
      messages,
    });
    const msg = await stream.finalMessage();
    if (msg.stop_reason === 'refusal') throw new Error(`planner refused: ${JSON.stringify(msg.stop_details)}`);
    const text = msg.content.flatMap((b) => (b.type === 'text' ? [b.text] : [])).join('');
    try {
      const parsed = PlanSchema.parse(extractJson(text));
      return sanitize(parsed.scenes as Scene[], t.duration);
    } catch (err) {
      if (msg.stop_reason === 'max_tokens') throw new Error('planner output truncated (max_tokens)');
      console.warn(`plan attempt ${attempt + 1} invalid: ${(err as Error).message.slice(0, 400)}`);
      messages.push({role: 'assistant', content: msg.content}, {role: 'user', content: `That JSON is invalid: ${(err as Error).message.slice(0, 2000)}\nReturn the corrected full JSON object only.`});
    }
  }
  throw new Error('planner failed to produce a valid plan');
};

export const emptyPlan = (video: string, src: {duration: number; fps: number; width: number; height: number}, s: Settings): Plan => ({
  video,
  duration: src.duration,
  fps: src.fps,
  width: s.render.width ?? src.width,
  height: s.render.height ?? src.height,
  film: s.film,
  sfx: s.sfx,
  scenes: [],
});
