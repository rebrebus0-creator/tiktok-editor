// Resolve every Asset in a plan into a local file under public/assets/<job>/.
import fs from 'node:fs';
import path from 'node:path';
import type {Asset, Plan, Scene} from '../src/types';
import {PUBLIC, type Settings} from './settings';

type Found = {url: string; kind: 'image' | 'video'; credit?: string};

const used = new Set<string>();

const pexelsPhoto = async (q: string, key: string): Promise<Found | null> => {
  const r = await fetch(`https://api.pexels.com/v1/search?query=${encodeURIComponent(q)}&per_page=15&orientation=landscape`, {
    headers: {Authorization: key},
  });
  if (!r.ok) throw new Error(`pexels ${r.status}: ${await r.text()}`);
  const j = (await r.json()) as {photos: {id: number; photographer: string; src: {large2x: string}}[]};
  const p = j.photos.find((x) => !used.has(`p${x.id}`)) ?? j.photos[0];
  if (!p) return null;
  used.add(`p${p.id}`);
  return {url: p.src.large2x, kind: 'image', credit: `${p.photographer} / Pexels`};
};

const pexelsVideo = async (q: string, key: string): Promise<Found | null> => {
  const r = await fetch(`https://api.pexels.com/videos/search?query=${encodeURIComponent(q)}&per_page=10&orientation=landscape`, {
    headers: {Authorization: key},
  });
  if (!r.ok) throw new Error(`pexels video ${r.status}: ${await r.text()}`);
  const j = (await r.json()) as {
    videos: {id: number; user: {name: string}; video_files: {link: string; width: number; file_type: string}[]}[];
  };
  for (const v of j.videos) {
    if (used.has(`v${v.id}`)) continue;
    const files = v.video_files.filter((f) => f.file_type === 'video/mp4' && f.width >= 1280).sort((a, b) => a.width - b.width);
    if (!files.length) continue;
    used.add(`v${v.id}`);
    return {url: files[0].link, kind: 'video', credit: `${v.user.name} / Pexels`};
  }
  return null;
};

/** fal.ai image generation (any text-to-image model id, e.g. fal-ai/flux/schnell). */
const falImage = async (prompt: string, s: Settings): Promise<Found | null> => {
  if (!s.fal?.apiKey) throw new Error('fal api key missing (settings.fal.apiKey or FAL_KEY)');
  const r = await fetch(`https://fal.run/${s.fal.model}`, {
    method: 'POST',
    headers: {Authorization: `Key ${s.fal.apiKey}`, 'Content-Type': 'application/json'},
    body: JSON.stringify({prompt: `${prompt}. ${s.styleHint}`, image_size: 'landscape_16_9', num_images: 1}),
  });
  if (!r.ok) throw new Error(`fal ${r.status}: ${await r.text()}`);
  const j = (await r.json()) as {images: {url: string}[]};
  return j.images[0] ? {url: j.images[0].url, kind: 'image', credit: s.fal.model} : null;
};

const download = async (url: string, file: string) => {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`download ${r.status} ${url}`);
  fs.writeFileSync(file, Buffer.from(await r.arrayBuffer()));
};

const resolveOne = async (a: Asset, id: string, job: string, s: Settings): Promise<void> => {
  if (a.src) return;
  const provider = a.provider ?? s.imageProvider;
  if (provider === 'placeholder' || provider === 'file') return;
  const q = a.query ?? a.prompt ?? '';
  for (const ext of ['jpg', 'mp4'] as const) {
    const rel = `assets/${job}/${id}.${ext}`;
    if (fs.existsSync(path.join(PUBLIC, rel))) {
      a.src = rel;
      a.kind = ext === 'mp4' ? 'video' : 'image';
      return;
    }
  }
  let found: Found | null = null;
  try {
    if (provider === 'gen' || provider === 'fal') {
      found = await falImage(a.prompt ?? q, s);
    } else {
      if (!s.pexelsApiKey) throw new Error('pexels api key missing (settings.pexelsApiKey or PEXELS_API_KEY)');
      if (a.kind === 'video' && s.stockVideo) found = await pexelsVideo(q, s.pexelsApiKey);
      found ??= await pexelsPhoto(q, s.pexelsApiKey);
    }
  } catch (err) {
    console.warn(`  ${id}: ${(err as Error).message.slice(0, 200)} -> placeholder`);
    return;
  }
  if (!found) {
    console.warn(`  ${id}: nothing found for "${q}" -> placeholder`);
    return;
  }
  const ext = found.kind === 'video' ? 'mp4' : 'jpg';
  const rel = `assets/${job}/${id}.${ext}`;
  const abs = path.join(PUBLIC, rel);
  if (!fs.existsSync(abs)) await download(found.url, abs);
  a.src = rel;
  a.kind = found.kind;
  a.credit = found.credit;
  console.log(`  ${id}: ${q} -> ${rel}`);
};

const assetsOf = (s: Scene): [Asset, string][] => {
  switch (s.type) {
    case 'photo':
    case 'split':
      return [[s.asset, s.id]];
    case 'polaroids':
    case 'board':
      return s.items.map((it, i) => [it.asset, `${s.id}_${i}`]);
    case 'label':
      return [];
    default:
      return s.bg ? [[s.bg, `${s.id}_bg`]] : [];
  }
};

/** Mutates the plan in place: fills `src` of every asset. Runs a few downloads in parallel. */
export const fetchAssets = async (plan: Plan, job: string, s: Settings, fresh = false): Promise<void> => {
  if (fresh) fs.rmSync(path.join(PUBLIC, 'assets', job), {recursive: true, force: true});
  fs.mkdirSync(path.join(PUBLIC, 'assets', job), {recursive: true});
  const all = plan.scenes.flatMap(assetsOf);
  const queue = [...all];
  const worker = async () => {
    for (let next = queue.shift(); next; next = queue.shift()) await resolveOne(next[0], next[1], job, s);
  };
  await Promise.all(Array.from({length: 4}, worker));
  const missing = all.filter(([a]) => !a.src).length;
  console.log(`assets: ${all.length - missing}/${all.length} resolved${missing ? `, ${missing} placeholders` : ''}`);
};
