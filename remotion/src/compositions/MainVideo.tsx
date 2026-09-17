import React from "react";
import { Series, useVideoConfig, Video } from "remotion";
import { VideoManifest } from "../types";
import { DynamicSubtitles } from "../components/DynamicSubtitles";

interface MainVideoProps {
  manifest: VideoManifest;
}

export const MainVideo: React.FC<MainVideoProps> = ({ manifest }) => {
  const { fps } = useVideoConfig();
  const isPortrait = manifest.aspectRatio === "9:16";

  const defaultBackgroundGradients = [
    "linear-gradient(135deg, #1e1b4b 0%, #312e81 100%)",
    "linear-gradient(135deg, #0f172a 0%, #1e293b 100%)",
    "linear-gradient(135deg, #18181b 0%, #27272a 100%)",
  ];

  return (
    <div
      style={{
        flex: 1,
        backgroundColor: "#000000",
        position: "relative",
        overflow: "hidden",
      }}
    >
      <Series>
        {manifest.scenes.map((scene, idx) => {
          const durationFrames = Math.max(1, Math.round(scene.durationSec * fps));
          const bgGradient = defaultBackgroundGradients[idx % defaultBackgroundGradients.length];

          return (
            <Series.Sequence key={scene.sceneId} durationInFrames={durationFrames}>
              <div
                style={{
                  width: "100%",
                  height: "100%",
                  position: "relative",
                  background: bgGradient,
                  display: "flex",
                  justifyContent: "center",
                  alignItems: "center",
                }}
              >
                {scene.videoUrl && scene.videoUrl.endsWith(".mp4") ? (
                  <Video
                    src={scene.videoUrl}
                    style={{
                      width: "100%",
                      height: "100%",
                      objectFit: "cover",
                    }}
                  />
                ) : (
                  // Visual Placeholder card for synthetic mock preview
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
                    <div
                      style={{
                        fontSize: isPortrait ? 28 : 20,
                        color: "#94A3B8",
                        maxWidth: "80%",
                        textAlign: "center",
                      }}
                    >
                      Duration: {scene.durationSec}s
                    </div>
                  </div>
                )}

                {/* Bottom Shadow Gradient for Subtitle Readability */}
                <div
                  style={{
                    position: "absolute",
                    bottom: 0,
                    left: 0,
                    right: 0,
                    height: isPortrait ? "40%" : "30%",
                    background: "linear-gradient(to top, rgba(0,0,0,0.85) 0%, transparent 100%)",
                    pointerEvents: "none",
                  }}
                />

                {/* Word-level dynamic subtitles */}
                <DynamicSubtitles
                  subtitles={scene.subtitles}
                  isPortrait={isPortrait}
                />
              </div>
            </Series.Sequence>
          );
        })}
      </Series>
    </div>
  );
};
