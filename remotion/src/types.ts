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

export interface ManifestScene {
  sceneId: number;
  title: string;
  videoUrl?: string;
  durationSec: number;
  voiceover: string;
  subtitles: WordTimestamp[];
  audioDucking: AudioDuckingConfig;
}

export interface VideoManifest {
  projectId: string;
  aspectRatio: "9:16" | "16:9";
  totalDurationSec: number;
  scenes: ManifestScene[];
  transitionType?: string;
}
