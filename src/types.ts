// Scene plan: the single contract between the pipeline (transcript -> plan -> assets)
// and the Remotion renderer. Times are in seconds of the source (avatar) video.

export type Grade = 'none' | 'cold' | 'sepia' | 'bw';

export type Asset = {
  /** Resolved file under public/ (e.g. "assets/s12.jpg") or an absolute URL. Filled by fetch-assets. */
  src?: string;
  kind?: 'image' | 'video';
  /** Stock search query (English works best for Pexels). */
  query?: string;
  /** Prompt for the image/video generator. */
  prompt?: string;
  /** Which provider should resolve this asset. Default: settings.defaultProvider. */
  provider?: 'pexels' | 'gen' | 'file' | 'placeholder';
  credit?: string;
};

/** Relative (0..1) coordinates of a red hand-drawn circle on a photo. */
export type Circle = {x: number; y: number; r: number};

type Base = {id: string; start: number; end: number};

export type PhotoScene = Base & {
  type: 'photo';
  asset: Asset;
  grade?: Grade;
  caption?: string;
  circle?: Circle;
  stamp?: string;
};

export type SplitScene = Base & {
  type: 'split';
  asset: Asset;
  /** Side where the avatar goes. */
  avatar?: 'left' | 'right';
  grade?: Grade;
  caption?: string;
};

export type NoteScene = Base & {
  type: 'note';
  /** Lines are typed out. Wrap words in [[double brackets]] to redact them with a black bar. */
  lines: string[];
  title?: string;
  stamp?: string;
  bg?: Asset;
  grade?: Grade;
};

export type QuoteScene = Base & {
  type: 'quote';
  text: string;
  author?: string;
  bg?: Asset;
  grade?: Grade;
};

export type ChecklistScene = Base & {
  type: 'checklist';
  items: string[];
  bg?: Asset;
  grade?: Grade;
};

export type NumbersScene = Base & {
  type: 'numbers';
  items: {value: number; label: string; prefix?: string; suffix?: string; decimals?: number}[];
  bg?: Asset;
  grade?: Grade;
};

export type PolaroidsScene = Base & {
  type: 'polaroids';
  items: {asset: Asset; caption: string}[];
  label?: string;
  bg?: Asset;
  grade?: Grade;
};

export type StampScene = Base & {
  type: 'stamp';
  text: string;
  bg?: Asset;
  grade?: Grade;
};

/** Lower-third paper strip over the avatar (place, name, date...). */
export type LabelScene = Base & {
  type: 'label';
  text: string;
  sub?: string;
};

/** Investigation board: photos pinned around a central card, linked with red string. */
export type BoardScene = Base & {
  type: 'board';
  items: {asset: Asset; caption: string}[];
  center?: string;
  label?: string;
};

export type Scene =
  | PhotoScene
  | SplitScene
  | NoteScene
  | QuoteScene
  | ChecklistScene
  | NumbersScene
  | PolaroidsScene
  | StampScene
  | LabelScene
  | BoardScene;

export type Plan = {
  /** Avatar video: path under public/ or absolute URL. */
  video: string;
  /** Duration of the avatar video in seconds (filled by the pipeline via ffprobe). */
  duration: number;
  fps: number;
  width: number;
  height: number;
  /** Global old-film look: grain, vignette, rounded frame. */
  film?: boolean;
  /** Sound effects on scene transitions. */
  sfx?: boolean;
  scenes: Scene[];
};

