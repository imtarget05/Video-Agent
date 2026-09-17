import React from "react";
import { Composition } from "remotion";
import { MainVideo } from "./compositions/MainVideo";
import { VideoManifest } from "./types";

const defaultManifest916: VideoManifest = {
  projectId: "sample_proj_916",
  aspectRatio: "9:16",
  totalDurationSec: 15.0,
  bgMusicUrl: "audio/bg_music.wav",
  scenes: [
    {
      sceneId: 1,
      title: "Hook",
      durationSec: 5.0,
      audioUrl: "audio/speech_scene_1.mp3",
      voiceover: "Bạn có biết điều này về AI không?",
      subtitles: [
        { word: "BẠN", start: 0.1, end: 0.6 },
        { word: "CÓ", start: 0.7, end: 1.2 },
        { word: "BIẾT", start: 1.3, end: 1.7 },
        { word: "ĐIỀU", start: 1.8, end: 2.3 },
        { word: "NÀY", start: 2.4, end: 2.8 },
        { word: "VỀ", start: 2.9, end: 3.3 },
        { word: "AI", start: 3.4, end: 4.1 },
        { word: "KHÔNG", start: 4.2, end: 5.0 },
      ],
      audioDucking: { musicVolumeNormal: 0.35, musicVolumeDucked: 0.1, duckDurationSec: 5.0 },
    },
    {
      sceneId: 2,
      title: "Core Solution",
      durationSec: 5.0,
      audioUrl: "audio/speech_scene_2.mp3",
      voiceover: "Hệ thống AI Agent kết hợp Remotion và Edge TTS",
      subtitles: [
        { word: "HỆ", start: 0.2, end: 0.8 },
        { word: "THỐNG", start: 0.9, end: 1.6 },
        { word: "AI", start: 1.7, end: 2.3 },
        { word: "AGENT", start: 2.4, end: 3.2 },
        { word: "REMOTION", start: 3.3, end: 4.5 },
      ],
      audioDucking: { musicVolumeNormal: 0.35, musicVolumeDucked: 0.1, duckDurationSec: 5.0 },
    },
    {
      sceneId: 3,
      title: "CTA",
      durationSec: 5.0,
      audioUrl: "audio/speech_scene_3.mp3",
      voiceover: "Theo dõi kênh ngay hôm nay để nhận thêm nhiều giải pháp!",
      subtitles: [
        { word: "THEO", start: 0.2, end: 0.9 },
        { word: "DÕI", start: 1.0, end: 1.8 },
        { word: "KÊNH", start: 1.9, end: 2.7 },
        { word: "NGAY", start: 2.8, end: 3.8 },
      ],
      audioDucking: { musicVolumeNormal: 0.35, musicVolumeDucked: 0.1, duckDurationSec: 5.0 },
    },
  ],
};

const defaultManifest169: VideoManifest = {
  ...defaultManifest916,
  projectId: "sample_proj_169",
  aspectRatio: "16:9",
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="Shorts916"
        component={MainVideo}
        durationInFrames={450}
        fps={30}
        width={1080}
        height={1920}
        calculateMetadata={({ props }) => {
          const m = (props as any).manifest || props;
          const totalSec = m?.totalDurationSec || 15.0;
          return {
            durationInFrames: Math.max(1, Math.round(totalSec * 30)),
          };
        }}
        defaultProps={{ manifest: defaultManifest916 }}
      />
      <Composition
        id="Landscape169"
        component={MainVideo}
        durationInFrames={450}
        fps={30}
        width={1920}
        height={1080}
        calculateMetadata={({ props }) => {
          const m = (props as any).manifest || props;
          const totalSec = m?.totalDurationSec || 15.0;
          return {
            durationInFrames: Math.max(1, Math.round(totalSec * 30)),
          };
        }}
        defaultProps={{ manifest: defaultManifest169 }}
      />
    </>
  );
};
