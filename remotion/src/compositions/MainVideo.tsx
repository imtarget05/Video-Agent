import React from "react";
import {
  Series,
  useCurrentFrame,
  useVideoConfig,
  Video,
  Audio,
  interpolate,
  staticFile,
} from "remotion";
import { ManifestScene, VideoManifest } from "../types";
import { DynamicSubtitles } from "../components/DynamicSubtitles";
import { KenBurnsImage } from "../components/KenBurnsImage";
import { AudioTrack } from "../components/AudioTrack";
import { BRollStitcher } from "../components/BRollStitcher";

export const FADE_FRAMES = 15;

interface MainVideoProps {
  manifest?: VideoManifest;
  projectId?: string;
  aspectRatio?: "9:16" | "16:9";
  totalDurationSec?: number;
  bgMusicUrl?: string;
  scenes?: any[];
}

/** Cumulative start offset (in seconds) of each scene on the global timeline. */
export const computeSceneOffsets = (scenes: ManifestScene[]): number[] => {
  const offsets: number[] = [];
  let acc = 0;
  for (const scene of scenes) {
    offsets.push(acc);
    acc += scene.durationSec;
  }
  return offsets;
};

interface SceneBodyProps {
  scene: ManifestScene;
  idx: number;
  durationFrames: number;
  isPortrait: boolean;
  sceneOffsetSec: number;
  bgGradient: string;
}

export const SceneBody: React.FC<SceneBodyProps> = ({
  scene,
  idx,
  durationFrames,
  isPortrait,
  sceneOffsetSec,
  bgGradient,
}) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(
    frame,
    [0, FADE_FRAMES, Math.max(FADE_FRAMES, durationFrames - FADE_FRAMES), durationFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        position: "relative",
        background: bgGradient,
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        opacity,
      }}
    >
      {/* Visual Media Layer: Real AI Image with Ken Burns OR Video Clip */}
      {scene.imageUrl ? (
        <KenBurnsImage
          imageSrc={scene.imageUrl}
          durationFrames={durationFrames}
          motion={scene.kenBurnsEffect || (idx % 2 === 0 ? "zoomIn" : "panLeft")}
        />
      ) : scene.videoUrl && scene.videoUrl.endsWith(".mp4") ? (
        <Video
          src={scene.videoUrl}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
          }}
        />
      ) : (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            color: "#FFFFFF",
            fontFamily: "sans-serif",
          }}
        >
          <div
            style={{
              fontSize: isPortrait ? 64 : 48,
              fontWeight: 800,
              color: "#38BDF8",
              marginBottom: 16,
            }}
          >
            Scene #{scene.sceneId}: {scene.title}
          </div>
        </div>
      )}

      {/* B-Roll secondary take (overlay full-cover or PiP card) */}
      {scene.bRollUrl && (
        <BRollStitcher
          bRollUrl={scene.bRollUrl}
          layout={scene.bRollLayout || "overlay"}
          isPortrait={isPortrait}
        />
      )}

      {/* Scene Voiceover Speech Audio */}
      {scene.audioUrl && <Audio src={staticFile(scene.audioUrl)} volume={1.0} />}

      {/* Bottom Shadow Gradient for Subtitle Readability */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          right: 0,
          height: isPortrait ? "45%" : "35%",
          background:
            "linear-gradient(to top, rgba(0,0,0,0.92) 0%, rgba(0,0,0,0.65) 45%, transparent 100%)",
          pointerEvents: "none",
        }}
      />

      {/* Word-level dynamic kinetic subtitles */}
      <DynamicSubtitles
        subtitles={scene.subtitles}
        sceneOffsetSec={sceneOffsetSec}
        isPortrait={isPortrait}
      />
    </div>
  );
};

export const MainVideo: React.FC<MainVideoProps> = (rawProps) => {
  const manifest: VideoManifest = rawProps.manifest || (rawProps as VideoManifest);
  const { fps } = useVideoConfig();
  const isPortrait = manifest.aspectRatio === "9:16";

  const defaultBackgroundGradients = [
    "linear-gradient(135deg, #1e1b4b 0%, #312e81 100%)",
    "linear-gradient(135deg, #0f172a 0%, #1e293b 100%)",
    "linear-gradient(135deg, #18181b 0%, #27272a 100%)",
  ];

  const bgMusic = manifest.bgMusicUrl || "audio/bg_music.wav";
  const scenes = manifest.scenes || [];
  const sceneOffsets = computeSceneOffsets(scenes as ManifestScene[]);
  const leadDucking = (scenes[0] as ManifestScene | undefined)?.audioDucking;

  return (
    <div
      style={{
        flex: 1,
        backgroundColor: "#000000",
        position: "relative",
        overflow: "hidden",
      }}
    >
      {/* Background Music Track with speech-ducking envelope */}
      <AudioTrack
        bgMusicUrl={staticFile(bgMusic)}
        duckingConfig={leadDucking}
        hasSpeech={scenes.some((s) => (s as ManifestScene).audioUrl)}
      />

      <Series>
        {scenes.map((scene, idx) => {
          const durationFrames = Math.max(1, Math.round(scene.durationSec * fps));
          const bgGradient = defaultBackgroundGradients[idx % defaultBackgroundGradients.length];

          return (
            <Series.Sequence key={scene.sceneId} durationInFrames={durationFrames}>
              <SceneBody
                scene={scene as ManifestScene}
                idx={idx}
                durationFrames={durationFrames}
                isPortrait={isPortrait}
                sceneOffsetSec={sceneOffsets[idx]}
                bgGradient={bgGradient}
              />
            </Series.Sequence>
          );
        })}
      </Series>
    </div>
  );
};
