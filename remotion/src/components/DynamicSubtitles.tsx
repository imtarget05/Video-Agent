import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { WordTimestamp } from "../types";

interface DynamicSubtitlesProps {
  subtitles: WordTimestamp[];
  sceneOffsetSec?: number;
  isPortrait?: boolean;
}

export const DynamicSubtitles: React.FC<DynamicSubtitlesProps> = ({
  subtitles,
  sceneOffsetSec = 0,
  isPortrait = true,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  // NOTE: inside <Series.Sequence> useCurrentFrame() is sequence-local,
  // so subtitles authored in scene-local seconds compare against local time.
  // sceneOffsetSec is the cumulative global offset of this scene (passed by
  // MainVideo.computeSceneOffsets) — kept for global-timeline mapping.
  const localTime = frame / fps;
  const currentTime = localTime;
  const globalTime = localTime + sceneOffsetSec;
  void globalTime;

  if (!subtitles || subtitles.length === 0) {
    return null;
  }

  // Find active or adjacent window of words
  return (
    <div
      style={{
        position: "absolute",
        bottom: isPortrait ? 220 : 80,
        left: 0,
        right: 0,
        display: "flex",
        flexWrap: "wrap",
        justifyContent: "center",
        alignItems: "center",
        padding: "0 40px",
        gap: "12px",
        zIndex: 50,
      }}
    >
      {subtitles.map((sub, idx) => {
        // Karaoke 3-state: past (spoken) / active (speaking) / future (upcoming)
        const isPast = currentTime > sub.end;
        const isActive = currentTime >= sub.start && currentTime <= sub.end;
        const isFuture = currentTime < sub.start;
        void isFuture;
        const color = isActive ? "#FACC15" : isPast ? "#FDE68A" : "#FFFFFF";
        const opacity = isPast ? 0.85 : 1.0;
        return (
          <span
            key={idx}
            style={{
              fontSize: isPortrait ? 52 : 38,
              fontWeight: 900,
              fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
              color,
              opacity,
              transform: isActive ? "scale(1.15)" : "scale(1.0)",
              transition: "transform 0.08s ease-in-out, color 0.08s ease-in-out",
              textShadow: "0 4px 16px rgba(0,0,0,0.85), 0 2px 4px rgba(0,0,0,0.9)",
              textTransform: "uppercase",
              letterSpacing: "1px",
            }}
          >
            {sub.word}
          </span>
        );
      })}
    </div>
  );
};
