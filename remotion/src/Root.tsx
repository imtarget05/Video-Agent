import React from "react";
import { Composition } from "remotion";
import { MainVideo } from "./compositions/MainVideo";
import { VideoManifest } from "./types";

const defaultManifest916: VideoManifest = {
  projectId: "sample_proj_916",
  aspectRatio: "9:16",
  totalDurationSec: 15.0,
  scenes: [
    {
      sceneId: 1,
      title: "Hook",
      durationSec: 4.0,
      voiceover: "Bí quyết tự động hóa video",
      subtitles: [
        { word: "BÍ", start: 0.1, end: 0.6 },
        { word: "QUYẾT", start: 0.7, end: 1.3 },
        { word: "TỰ", start: 1.4, end: 2.0 },
        { word: "ĐỘNG", start: 2.1, end: 2.7 },
        { word: "HÓA", start: 2.8, end: 3.5 },
      ],
      audioDucking: { musicVolumeNormal: 0.35, musicVolumeDucked: 0.1, duckDurationSec: 4.0 },
    },
    {
      sceneId: 2,
      title: "Core Solution",
      durationSec: 6.0,
      voiceover: "Hệ thống AI Agent kết hợp Remotion",
      subtitles: [
        { word: "HỆ", start: 0.2, end: 0.8 },
        { word: "THỐNG", start: 0.9, end: 1.6 },
        { word: "AI", start: 1.7, end: 2.3 },
        { word: "AGENT", start: 2.4, end: 3.2 },
        { word: "REMOTION", start: 3.3, end: 4.5 },
      ],
      audioDucking: { musicVolumeNormal: 0.35, musicVolumeDucked: 0.1, duckDurationSec: 6.0 },
    },
    {
      sceneId: 3,
      title: "CTA",
      durationSec: 5.0,
      voiceover: "Theo dõi kênh ngay hôm nay",
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
        durationInFrames={450} // 15s * 30fps
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{ manifest: defaultManifest916 }}
      />
      <Composition
        id="Landscape169"
        component={MainVideo}
        durationInFrames={450} // 15s * 30fps
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{ manifest: defaultManifest169 }}
      />
    </>
  );
};
