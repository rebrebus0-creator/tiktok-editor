import path from 'node:path';
import {bundle} from '@remotion/bundler';
import {renderMedia, selectComposition} from '@remotion/renderer';
import type {Plan} from '../src/types';
import {ROOT, type Settings} from './settings';

export const renderPlan = async (plan: Plan, outFile: string, s: Settings): Promise<void> => {
  console.log('bundling...');
  const serveUrl = await bundle({entryPoint: path.join(ROOT, 'src/index.ts'), publicDir: path.join(ROOT, 'public')});
  const browserExecutable = s.render.browserExecutable ?? process.env.REMOTION_BROWSER ?? null;
  const inputProps = plan as unknown as Record<string, unknown>;
  const composition = await selectComposition({serveUrl, id: 'Main', inputProps, browserExecutable});
  console.log(`rendering ${composition.durationInFrames} frames at ${composition.width}x${composition.height}...`);
  let last = -1;
  await renderMedia({
    serveUrl,
    composition,
    inputProps,
    codec: 'h264',
    crf: s.render.crf,
    audioCodec: 'aac',
    outputLocation: outFile,
    concurrency: s.render.concurrency,
    browserExecutable,
    onProgress: ({progress}) => {
      const pct = Math.floor(progress * 100);
      if (pct !== last && pct % 5 === 0) {
        last = pct;
        console.log(`  ${pct}%`);
      }
    },
  });
  console.log(`done: ${outFile}`);
};
