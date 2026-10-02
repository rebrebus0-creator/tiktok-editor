import {loadFont} from '@remotion/fonts';
import {staticFile} from 'remotion';
import type {Grade} from '../types';

export const C = {
  paper: '#e8dcc0',
  paperDark: '#cbb98f',
  ink: '#1d1a16',
  red: '#b01822',
  tape: 'rgba(236, 230, 212, 0.78)',
};

export const MONO = '"PT Mono", "Courier New", monospace';
export const HEAD = '"Oswald", "Arial Narrow", sans-serif';

const fonts: [string, string, string][] = [
  ['PT Mono', 'pt-mono-cyrillic-400-normal.woff2', '400'],
  ['PT Mono', 'pt-mono-latin-400-normal.woff2', '400'],
  ['Oswald', 'oswald-cyrillic-700-normal.woff2', '700'],
  ['Oswald', 'oswald-latin-700-normal.woff2', '700'],
];
for (const [family, file, weight] of fonts) {
  loadFont({family, url: staticFile(`fonts/${file}`), weight});
}

export const gradeFilter = (g: Grade = 'none'): string => {
  switch (g) {
    case 'cold':
      return 'saturate(0.5) contrast(1.1) brightness(0.9)';
    case 'sepia':
      return 'sepia(0.55) saturate(0.8) contrast(1.05) brightness(0.9)';
    case 'bw':
      return 'grayscale(1) contrast(1.15) brightness(0.92)';
    default:
      return 'none';
  }
};
