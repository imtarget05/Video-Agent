export interface WordTimestamp {
  word: string;
  start: number;
  end: number;
}

export interface AudioDuckingConfig {
  musicVolumeNormal: number;
  musicVolumeDucked: number;
  duckDurationSec: number;
}

export type KenBurnsMotion = "zoomIn" | "zoomOut" | "panLeft" | "panRight";

export type BRollLayout = "overlay" | "pip";

export interface ManifestScene {
  sceneId: number;
  title: string;
  videoUrl?: string;
  imageUrl?: string;
  kenBurnsEffect?: KenBurnsMotion;
  audioUrl?: string;
  durationSec: number;
  voiceover: string;
  subtitles: WordTimestamp[];
  audioDucking?: AudioDuckingConfig;
  bRollUrl?: string;
  bRollLayout?: BRollLayout;
}

export interface VideoManifest {
  projectId: string;
  aspectRatio: "9:16" | "16:9";
  totalDurationSec: number;
  bgMusicUrl?: string;
  scenes: ManifestScene[];
  transitionType?: string;
}
